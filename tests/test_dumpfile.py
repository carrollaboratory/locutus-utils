import datetime
import gzip
import stat

import bson
import pytest
from bson import Binary, Decimal128, Int64, ObjectId

from locutils.dbcopy import DbCopyError
from locutils.dbcopy.dumpfile import FORMAT, FORMAT_VERSION, DumpWriter, read_dump, to_json

HEADER = {"format": FORMAT, "format_version": FORMAT_VERSION, "scope": {"kind": "full"}}

TRICKY = {
    "_id": ObjectId("6af4a8acc40ddd1e3599242f"),
    "date": datetime.datetime(2026, 3, 4, 5, 6, 7, 123000),
    "none": None,
    "small_long": Int64(5),
    "big_long": Int64(2**40),
    "nested": [[1, 2.0, {"a": [Int64(7)]}]],
    "dec": Decimal128("1.10"),
    "bin": Binary(b"\x00\x01"),
    "neg0": -0.0,
    "text": "héllo",
}


def write(path, collections, header=HEADER):
    with DumpWriter(path, header) as w:
        for name, docs in collections.items():
            w.write_collection(name, [], docs)


def test_small_int64_keeps_its_type():
    assert to_json({"n": Int64(5)}) == '{"n": {"$numberLong": "5"}}'
    assert to_json({"n": 5}) == '{"n": 5}'


@pytest.mark.parametrize("name", ["d.locutus.json", "d.locutus.json.gz"])
def test_round_trip_keeps_types(tmp_path, name):
    path = tmp_path / name
    write(path, {"User": [TRICKY]})
    data = read_dump(path)
    doc = data["collections"]["User"]["documents"][0]
    # Same BSON bytes means same values and types. (Binary subtype 0 reads
    # back as bytes, as it does from Mongo itself, but encodes the same.)
    assert bson.encode(doc) == bson.encode(TRICKY)
    assert type(doc["small_long"]) is Int64
    assert type(doc["nested"][0][2]["a"][0]) is Int64
    assert data["collections"]["User"]["count"] == 1


def test_gzip_bytes_depend_only_on_content(tmp_path):
    a, b = tmp_path / "a.json.gz", tmp_path / "b.json.gz"
    write(a, {"User": [TRICKY]})
    write(b, {"User": [TRICKY]})
    assert a.read_bytes() == b.read_bytes()


def test_one_document_per_line(tmp_path):
    path = tmp_path / "d.json"
    docs = [{"_id": i, "v": "x"} for i in range(3)]
    write(path, {"T": docs})
    lines = [l.strip().rstrip(",") for l in path.read_text().splitlines()]
    for d in docs:
        assert to_json(d) in lines


def test_empty_collection(tmp_path):
    path = tmp_path / "d.json"
    write(path, {"Empty": []})
    entry = read_dump(path)["collections"]["Empty"]
    assert entry["documents"] == [] and entry["count"] == 0


def test_file_is_owner_only(tmp_path):
    path = tmp_path / "d.json.gz"
    write(path, {"User": [TRICKY]})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_failure_leaves_no_file(tmp_path):
    path = tmp_path / "d.json.gz"

    def docs():
        yield {"_id": 1}
        raise RuntimeError("source went away")

    with pytest.raises(RuntimeError):
        write(path, {"User": docs()})
    assert list(tmp_path.iterdir()) == []


def test_failure_keeps_existing_file(tmp_path):
    path = tmp_path / "d.json"
    path.write_text("previous")
    with pytest.raises(RuntimeError):
        with DumpWriter(path, HEADER):
            raise RuntimeError("boom")
    assert path.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [path]


def test_read_missing_file(tmp_path):
    with pytest.raises(DbCopyError, match="does not exist"):
        read_dump(tmp_path / "nope.json")


def test_read_truncated_gzip(tmp_path):
    path = tmp_path / "d.json.gz"
    write(path, {"User": [TRICKY] * 50})
    raw = path.read_bytes()
    path.write_bytes(raw[: len(raw) // 2])
    with pytest.raises(DbCopyError, match="truncated"):
        read_dump(path)


def test_read_gzip_detected_by_content(tmp_path):
    path = tmp_path / "renamed.json"
    path.write_bytes(gzip.compress(b'{"format": "locutus-dump", "collections": {}}'))
    assert read_dump(path)["format"] == FORMAT


def test_read_not_a_dump(tmp_path):
    path = tmp_path / "other.json"
    path.write_text('{"something": "else"}')
    with pytest.raises(DbCopyError, match="not a Locutus dump"):
        read_dump(path)
