"""Dump and load against a real MongoDB server (see conftest.py)."""

import datetime
import json

import pytest
from bson import Binary, Decimal128, Int64, ObjectId
from pymongo.collection import Collection

from conftest import snapshot
from locutils.dbcopy import DbCopyError, cli
from locutils.dbcopy import load as load_module
from locutils.dbcopy.dump import run_dump
from locutils.dbcopy.dumpfile import read_dump
from locutils.dbcopy.load import run_load

pytestmark = pytest.mark.mongo

LOGIN = datetime.datetime(2026, 3, 4, 5, 6, 7, 123000)


def fill(db):
    """A small database covering the BSON types and _id kinds Locutus uses."""
    db.User.insert_one({
        "_id": ObjectId(),
        "email": "someone@example.org",
        "lastLoginAt": LOGIN,
        "disabledAt": None,
        "nested": [[1, 2.0, {"a": [Int64(5), Int64(2**40)]}]],
        "dec": Decimal128("1.10"),
        "bin": Binary(b"\x00\x01"),
        "big": 2**40,
        "neg0": -0.0,
    })
    db.Config.insert_one({"id": "bootstrap", "adminEmails": ["a@example.org"]})
    db.Terminology.insert_one({"_id": "string-id", "v": 1})
    db.Institution.insert_one({"_id": "vumc", "name": "VUMC", "x": 1})
    db.Institution.create_index([("name", 1), ("x", -1)], name="name_x", unique=True, sparse=True)


@pytest.fixture
def source(scratch_db, tmp_path):
    """A filled source database and a dump of it."""
    uri, db = scratch_db()
    fill(db)
    path = tmp_path / "src.locutus.json.gz"
    run_dump(uri, path, source_version="v2.3.1")
    return db, path


@pytest.fixture
def target(scratch_db):
    return scratch_db()


def load(uri, path, **kw):
    kw.setdefault("yes", True)
    kw.setdefault("target_version", "v2.3.1")
    run_load(uri, path, **kw)


def working_collections(db):
    return [n for n in db.list_collection_names() if n.startswith(("_load_", "_prev_"))]


def test_round_trip_is_exact(source, target):
    src, path = source
    uri, dst = target
    load(uri, path)
    assert snapshot(dst) == snapshot(src)
    assert dst.User.find_one()["lastLoginAt"] == LOGIN
    assert working_collections(dst) == []


def test_indexes_recreated(source, target):
    _, path = source
    uri, dst = target
    load(uri, path)
    idx = dst.Institution.index_information()["name_x"]
    assert idx["unique"] and idx["sparse"]
    assert idx["key"] == [("name", 1), ("x", -1)]


def test_dump_header_and_order(source):
    src, path = source
    data = read_dump(path)
    assert data["scope"] == {"kind": "full"}
    assert data["source"]["database"] == src.name
    assert data["source"]["locutus_version"] == "v2.3.1"
    assert sorted(data["collections"]) == ["Config", "Institution", "Terminology", "User"]


def test_dump_skips_sessions_tokens_and_leftovers(scratch_db, tmp_path):
    uri, db = scratch_db()
    fill(db)
    db.sessions.insert_one({"_id": "s"})
    db.ApiToken.insert_one({"_id": "t"})
    db["_prev_20260101T000000__User"].insert_one({"_id": 1})
    run_dump(uri, tmp_path / "a.json")
    assert set(read_dump(tmp_path / "a.json")["collections"]) == {"Config", "Institution", "Terminology", "User"}
    run_dump(uri, tmp_path / "b.json", include_tokens=True)
    assert "ApiToken" in read_dump(tmp_path / "b.json")["collections"]


def test_dump_empty_database_refused(scratch_db, tmp_path):
    uri, _ = scratch_db()
    with pytest.raises(DbCopyError, match="no collections"):
        run_dump(uri, tmp_path / "x.json")
    assert not (tmp_path / "x.json").exists()


def test_refuses_occupied_target_without_replace(source, target):
    _, path = source
    uri, dst = target
    dst.User.insert_one({"existing": True})
    before = snapshot(dst)
    with pytest.raises(DbCopyError, match="--replace"):
        load(uri, path)
    assert snapshot(dst) == before


def test_replace_swaps_and_clears_sessions(source, target):
    src, path = source
    uri, dst = target
    dst.User.insert_one({"existing": True})
    dst.sessions.insert_one({"_id": "s"})
    dst.Study.insert_one({"_id": "untouched"})
    load(uri, path, replace=True)
    assert dst.User.count_documents({}) == 1
    assert dst.sessions.count_documents({}) == 0
    assert dst.Study.count_documents({}) == 1  # not in the dump, left alone
    assert working_collections(dst) == []
    assert snapshot(dst)["User"] == snapshot(src)["User"]


def test_keep_previous(source, target):
    _, path = source
    uri, dst = target
    load(uri, path)
    load(uri, path, replace=True, keep_previous=True)
    prev = [n for n in dst.list_collection_names() if n.startswith("_prev_")]
    assert len(prev) == 4


def test_staging_failure_leaves_target_untouched(source, target, monkeypatch):
    _, path = source
    uri, dst = target
    load(uri, path)
    dst.User.insert_one({"marker": 1})
    before = snapshot(dst)

    real = load_module.insert_all
    calls = {"n": 0}

    def fail_third(coll, docs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("simulated staging failure")
        real(coll, docs)

    monkeypatch.setattr(load_module, "insert_all", fail_third)
    with pytest.raises(RuntimeError, match="staging"):
        load(uri, path, replace=True)
    assert snapshot(dst) == before


def test_swap_failure_rolls_back(source, target, monkeypatch):
    _, path = source
    uri, dst = target
    load(uri, path)
    dst.User.insert_one({"marker": 1})
    before = snapshot(dst)

    real = Collection.rename
    calls = {"n": 0}

    def fail_fourth(self, new_name, **kw):
        if not self.name.endswith("__probe"):
            calls["n"] += 1
            if calls["n"] == 4:
                raise RuntimeError("simulated swap failure")
        return real(self, new_name, **kw)

    monkeypatch.setattr(Collection, "rename", fail_fourth)
    with pytest.raises(RuntimeError, match="swap"):
        load(uri, path, replace=True)
    assert snapshot(dst) == before


def test_in_place_when_rename_unsupported(source, target, monkeypatch, capsys):
    """The Firestore path, simulated: no staging collections at all."""
    src, path = source
    uri, dst = target
    dst.User.insert_one({"existing": True})
    monkeypatch.setattr(load_module, "supports_rename", lambda db, run_id: False)
    load(uri, path, replace=True)
    assert "runs in place" in capsys.readouterr().err
    assert snapshot(dst) == snapshot(src)


@pytest.mark.parametrize(
    "break_it, message",
    [
        (lambda d: d.update(format_version=99), "format version 99"),
        (lambda d: d["collections"]["User"].update(count=7), "header says 7"),
    ],
)
def test_bad_dump_writes_nothing(source, target, tmp_path, break_it, message):
    _, path = source
    uri, dst = target
    dst.Study.insert_one({"_id": "keep"})
    before = snapshot(dst)
    data = json.loads(json.dumps(read_dump(path), default=str))
    break_it(data)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(DbCopyError, match=message):
        load(uri, bad, replace=True)
    assert snapshot(dst) == before


def test_cli(source, target, tmp_path, capsys):
    src_db, _ = source
    uri, dst = target
    src_uri = uri.replace(dst.name, src_db.name)
    out = tmp_path / "cli.locutus.json.gz"

    assert cli.main(["dump", "-db", src_uri, "-o", str(out), "--locutus-version", "v2.3.1"]) == 0
    assert cli.main(["dump", "-db", src_uri, "-o", str(out)]) == 1
    assert "--force" in capsys.readouterr().err
    assert cli.main(["dump", "-db", src_uri, "-o", str(out), "--force", "--locutus-version", "v2.3.1"]) == 0

    assert cli.main(["load", "-db", uri, "-i", str(out), "--yes", "--target-version", "v2.3.1"]) == 0
    assert cli.main(["load", "-db", uri, "-i", str(out), "--yes", "--target-version", "v2.3.1"]) == 1
    assert "--replace" in capsys.readouterr().err
    assert snapshot(dst) == snapshot(src_db)
