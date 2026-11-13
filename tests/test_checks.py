"""Checks that run without a database: release comparison, the load
preflight, URI handling and collection selection."""

import copy

import pytest

from locutils.dbcopy import DbCopyError, filter_uri, is_known_collection, versions
from locutils.dbcopy.dump import choose_collections
from locutils.dbcopy.load import confirm, is_local, preflight


def dump_with(**collections):
    return {
        "format": "locutus-dump",
        "format_version": 1,
        "scope": {"kind": "full"},
        "source": {"locutus_version": "v2.3.1"},
        "collections": {
            name: {"indexes": [], "documents": docs, "count": len(docs)}
            for name, docs in collections.items()
        },
    }


GOOD = dump_with(User=[{"_id": 1}], Institution=[{"_id": "vumc"}], Config=[{"_id": "c"}])


@pytest.fixture
def breaking(monkeypatch):
    monkeypatch.setattr(versions, "BREAKING_RELEASES", ["v2.4.0"])


# --- releases

@pytest.mark.parametrize(
    "text, expected",
    [
        ("v2.3.1", (2, 3, 1)),
        ("2.3.1.dev4+gabc", (2, 3, 1)),
        ("v3", (3,)),
        ("local", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_release(text, expected):
    assert versions.parse_release(text) == expected


def test_same_release_is_silent(capsys):
    versions.check_versions("v2.3.1", "2.3.1")
    assert capsys.readouterr().err == ""


def test_unknown_release_warns(capsys):
    versions.check_versions("local", None)
    err = capsys.readouterr().err
    assert "release check was skipped" in err and "local" in err


def test_different_release_warns(capsys):
    versions.check_versions("v2.3.1", "v2.5.0")
    assert "No breaking release" in capsys.readouterr().err


def test_crossing_breaking_release_refused(breaking):
    with pytest.raises(DbCopyError, match="--allow-breaking"):
        versions.check_versions("v2.3.1", "v2.5.0")
    with pytest.raises(DbCopyError):
        versions.check_versions("v2.5.0", "v2.3.1")  # downgrades too


def test_crossing_breaking_release_allowed(breaking, capsys):
    versions.check_versions("v2.3.1", "v2.5.0", allow_breaking=True)
    assert "v2.4.0" in capsys.readouterr().err


def test_breaking_release_boundaries(breaking):
    versions.check_versions("v2.4.0", "v2.5.0")  # both already past it
    with pytest.raises(DbCopyError):
        versions.check_versions("v2.3.9", "v2.4.0")


def test_url_and_version_together_refused():
    with pytest.raises(DbCopyError, match="not both"):
        versions.resolve_version("https://x", "v1", "target")


# --- preflight

def test_preflight_accepts_good_dump():
    assert set(preflight(copy.deepcopy(GOOD), target_version="v2.3.1")) == {"User", "Institution", "Config"}


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d.update(format_version=99), "format version 99"),
        (lambda d: d.update(format_version="1"), "no valid format_version"),
        (lambda d: d.update(scope={"kind": "study"}), "only load full dumps"),
        (lambda d: d.update(collections={}), "no collections"),
        (lambda d: d["collections"]["User"].update(count=7), "header says 7"),
        (lambda d: d["collections"]["User"]["documents"].append({"_id": 1}), "duplicate _id"),
        (lambda d: d["collections"]["User"]["documents"].append({"x": 1}), "has no _id"),
        (lambda d: d["collections"].update({"_load_x__User": d["collections"]["User"]}), "not a collection name"),
        (lambda d: d["collections"].update({"system.views": d["collections"]["User"]}), "not a collection name"),
        (lambda d: d["collections"]["User"].update(documents=None), "no document list"),
    ],
)
def test_preflight_refusals(change, message):
    dump = copy.deepcopy(GOOD)
    change(dump)
    if message != "header says 7":
        for entry in dump["collections"].values():
            if isinstance(entry.get("documents"), list):
                entry["count"] = len(entry["documents"])
    with pytest.raises(DbCopyError, match=message):
        preflight(dump, target_version="v2.3.1")


def test_preflight_refuses_oversized_document():
    dump = dump_with(User=[{"_id": 1, "blob": "x" * (16 * 1024 * 1024)}])
    with pytest.raises(DbCopyError, match="16 MB"):
        preflight(dump, target_version="v2.3.1")


def test_preflight_same_id_in_different_types_is_fine():
    dump = dump_with(User=[{"_id": 1}, {"_id": "1"}, {"_id": 1.5}])
    assert "User" in preflight(dump, target_version="v2.3.1")


def test_preflight_ignores_sessions(capsys):
    dump = copy.deepcopy(GOOD)
    dump["collections"]["sessions"] = {"indexes": [], "documents": [{"_id": "s"}], "count": 1}
    assert "sessions" not in preflight(dump, target_version="v2.3.1")
    assert "login sessions are never copied" in capsys.readouterr().err


def test_preflight_warns_without_core_collections(capsys):
    preflight(dump_with(Terminology=[{"_id": 1}]), target_version="v2.3.1")
    assert "User, Institution, Config" in capsys.readouterr().err


def test_preflight_checks_releases(breaking):
    with pytest.raises(DbCopyError, match="--allow-breaking"):
        preflight(copy.deepcopy(GOOD), target_version="v2.5.0")
    preflight(copy.deepcopy(GOOD), target_version="v2.5.0", allow_breaking=True)


# --- URIs, collections, confirmation

@pytest.mark.parametrize(
    "uri, masked",
    [
        ("mongodb://u:secret@h:27017/db", "mongodb://u:****@h:27017/db"),
        ("mongodb+srv://u:p%40ss@cluster.example.net/db?tls=true", "mongodb+srv://u:****@cluster.example.net/db?tls=true"),
        ("mongodb://h:27017/db", "mongodb://h:27017/db"),
    ],
)
def test_filter_uri(uri, masked):
    assert filter_uri(uri) == masked


@pytest.mark.parametrize(
    "uri, local",
    [
        ("mongodb://u:p@127.0.0.1:27017/db", True),
        ("mongodb://u:p@mongo:27017/db?authSource=admin", True),
        ("mongodb://localhost,127.0.0.1/db", True),
        ("mongodb://localhost,db.example.org/db", False),
        ("mongodb://u:p@host.docker.internal:27017/db", False),
        ("not a uri", False),
    ],
)
def test_is_local(uri, local):
    assert is_local(uri) is local


def test_choose_collections(capsys):
    names = ["User", "sessions", "ApiToken", "system.views", "_load_x__User", "_prev_x__User", "Brand_New", "Study__a__b"]
    chosen, skipped = choose_collections(names, include_tokens=False)
    assert chosen == ["Brand_New", "Study__a__b", "User"]
    assert {n for n, _ in skipped} == {"sessions", "ApiToken", "_load_x__User", "_prev_x__User"}
    err = capsys.readouterr().err
    assert "Brand_New isn't a collection" in err and "Study__a__b" not in err

    chosen, _ = choose_collections(names, include_tokens=True)
    assert "ApiToken" in chosen


def test_is_known_collection():
    assert is_known_collection("Terminology")
    assert is_known_collection("Study__123__tables")
    assert not is_known_collection("Nope")


def test_confirm_needs_terminal(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(DbCopyError, match="--yes"):
        confirm("locutus", local=True, yes=False)
    confirm("locutus", local=True, yes=True)


@pytest.mark.parametrize(
    "answers, local, ok",
    [
        (["locutus"], True, True),
        (["wrong"], True, False),
        (["y", "locutus"], False, True),
        (["n"], False, False),
        ([""], False, False),
    ],
)
def test_confirm_prompts(monkeypatch, answers, local, ok):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    if ok:
        confirm("locutus", local=local, yes=False)
    else:
        with pytest.raises(DbCopyError, match="cancelled"):
            confirm("locutus", local=local, yes=False)
