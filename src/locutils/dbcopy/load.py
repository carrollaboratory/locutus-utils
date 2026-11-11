"""locutils load: copy a dump into a Locutus database, all or nothing.

The loader never writes to a real collection until everything is in place:

  1. Stage   Insert each collection into _load_<run>__<name> and build its
             indexes. Any failure drops the staging collections, leaving
             the target untouched.
  2. Swap    Rename each real collection being replaced to
             _prev_<run>__<name>, then rename the staged copy to the real
             name. Each rename is atomic. If one fails, everything already
             swapped is put back.
  3. Clean   Drop the _prev_ collections, unless --keep-previous.

A single transaction can't do this reliably: transactions need a replica
set, time out after about a minute and can't drop collections.

Targets that don't support renameCollection (Firestore's MongoDB API) are
loaded in place instead, relying on the database's own backups for
recovery, which is why the confirmation asks about a recent backup.
"""

import sys
from datetime import UTC, datetime

import bson
from pymongo.errors import PyMongoError
from pymongo.uri_parser import parse_uri

from . import (
    ALWAYS_SKIP,
    CORE_COLLECTIONS,
    PREVIOUS_PREFIX,
    STAGING_PREFIX,
    DbCopyError,
    filter_uri,
    print_counts,
    warn,
)
from .dump import connect
from .dumpfile import FORMAT_VERSION, read_dump
from .versions import check_versions

BATCH_SIZE = 500
MAX_BSON_SIZE = 16 * 1024 * 1024
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "mongo"}


def preflight(dump, allow_breaking=False, target_version=None):
    """Check everything that can be checked without touching the target.
    Returns the collections to load."""
    version = dump.get("format_version")
    if not isinstance(version, int) or version < 1:
        raise DbCopyError("The dump has no valid format_version.")
    if version > FORMAT_VERSION:
        raise DbCopyError(
            f"The dump uses format version {version}, but this locutils only reads up to "
            f"{FORMAT_VERSION}. Update locutils and try again."
        )

    kind = (dump.get("scope") or {}).get("kind")
    if kind != "full":
        raise DbCopyError(f"This locutils can only load full dumps, not '{kind}' dumps.")

    source = dump.get("source") or {}
    check_versions(source.get("locutus_version"), target_version, allow_breaking)

    collections = dump.get("collections")
    if not isinstance(collections, dict) or not collections:
        raise DbCopyError("The dump contains no collections.")

    problems = []
    to_load = {}
    for name, entry in sorted(collections.items()):
        if name in ALWAYS_SKIP:
            warn(f"Ignoring {name} in the dump; login sessions are never copied.")
            continue
        if (
            not name
            or name.startswith(("system.", STAGING_PREFIX, PREVIOUS_PREFIX))
            or "$" in name
            or "\0" in name
        ):
            problems.append(f"{name!r} is not a collection name the loader will write.")
            continue

        docs = entry.get("documents")
        if not isinstance(docs, list):
            problems.append(f"{name}: no document list.")
            continue
        if entry.get("count") != len(docs):
            problems.append(f"{name}: header says {entry.get('count')} documents, the file has {len(docs)}.")

        seen = set()
        for i, doc in enumerate(docs):
            if not isinstance(doc, dict) or "_id" not in doc:
                problems.append(f"{name}: document {i} has no _id.")
                break
            key = bson.encode({"k": doc["_id"]})
            if key in seen:
                problems.append(f"{name}: duplicate _id {doc['_id']!r}.")
                break
            seen.add(key)
            if len(bson.encode(doc)) > MAX_BSON_SIZE:
                problems.append(f"{name}: document {doc['_id']!r} is over Mongo's 16 MB limit.")
                break
        to_load[name] = entry

    if problems:
        raise DbCopyError("The dump failed its checks; nothing was written:\n  " + "\n  ".join(problems))

    missing_core = [c for c in CORE_COLLECTIONS if c not in to_load]
    if missing_core:
        warn(f"The dump has no {', '.join(missing_core)} collection(s). The target won't have those accounts, institutions or admins.")
    return to_load


def is_local(uri):
    try:
        nodes = parse_uri(uri)["nodelist"]
    except Exception:  # noqa: BLE001
        return False
    return bool(nodes) and all(host in LOCAL_HOSTS for host, _ in nodes)


def confirm(db_name, local, yes):
    if yes:
        return
    if not sys.stdin.isatty():
        raise DbCopyError("No terminal to confirm on. Pass --yes to load without a prompt.")
    if not local:
        answer = input(f"{db_name} is not a local database. Has a recent backup of it been taken? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            raise DbCopyError("Load cancelled. Take a backup first.")
    typed = input(f"Type the database name ({db_name}) to load into it: ")
    if typed.strip() != db_name:
        raise DbCopyError("The name didn't match. Load cancelled; nothing was written.")


def insert_all(collection, docs):
    for start in range(0, len(docs), BATCH_SIZE):
        collection.insert_many(docs[start : start + BATCH_SIZE], ordered=True)


def create_indexes(collection, specs, label):
    for spec in specs:
        try:
            collection.create_index(
                [(field, direction) for field, direction in spec["key"]],
                name=spec["name"],
                **spec.get("options", {}),
            )
        except PyMongoError as e:
            warn(f"Unable to create index {spec['name']} on {label} ({e}). Locutus rebuilds its own indexes at startup.")


def drop_quietly(db, names):
    for name in names:
        try:
            db.drop_collection(name)
        except PyMongoError as e:
            warn(f"Unable to drop {name} ({e}); drop it by hand.")


def supports_rename(db, run_id):
    first = f"{STAGING_PREFIX}{run_id}__probe"
    second = f"{first}_renamed"
    try:
        db[first].insert_one({"probe": True})
        db[first].rename(second)
        return True
    except PyMongoError:
        return False
    finally:
        drop_quietly(db, [first, second])


def stage(db, collections, run_id):
    staged = {}
    try:
        for name, entry in collections.items():
            staging = f"{STAGING_PREFIX}{run_id}__{name}"
            db.create_collection(staging)
            staged[name] = staging
            insert_all(db[staging], entry["documents"])
            written = db[staging].count_documents({})
            if written != entry["count"]:
                raise DbCopyError(f"Staged {written} {name} documents, expected {entry['count']}.")
            create_indexes(db[staging], entry.get("indexes", []), name)
            print(f"  staged {name} ({written})")
    except BaseException:
        print("Staging failed; dropping the staged collections. The target was not changed.", file=sys.stderr)
        drop_quietly(db, staged.values())
        raise
    return staged


def swap(db, staged, existing, run_id):
    """Swap staged collections in. Returns {name: previous collection}."""
    previous = {}
    swapped = []
    try:
        for name, staging in staged.items():
            if name in existing:
                prev = f"{PREVIOUS_PREFIX}{run_id}__{name}"
                db[name].rename(prev)
                previous[name] = prev
            db[staging].rename(name)
            swapped.append(name)
    except BaseException as e:
        print(f"Swap failed ({e!r}); restoring the previous collections.", file=sys.stderr)
        stuck = []
        for name in swapped:
            try:
                db.drop_collection(name)
            except PyMongoError:
                stuck.append(name)
        for name, prev in previous.items():
            try:
                db[prev].rename(name)
            except PyMongoError:
                stuck.append(f"{prev} -> {name}")
        drop_quietly(db, [s for n, s in staged.items() if n not in swapped])
        if stuck:
            raise DbCopyError(
                "The swap failed and these collections could not be restored automatically: "
                + ", ".join(stuck)
                + f". The originals are in the {PREVIOUS_PREFIX}{run_id}__* collections."
            ) from e
        if isinstance(e, DbCopyError | PyMongoError):
            raise DbCopyError(f"The swap failed ({e}). The target was restored to its previous state.") from e
        raise
    return previous


def load_in_place(db, collections, existing):
    for name, entry in collections.items():
        if name in existing:
            db[name].delete_many({})
        insert_all(db[name], entry["documents"])
        create_indexes(db[name], entry.get("indexes", []), name)
        print(f"  loaded {name} ({entry['count']})")


def run_load(uri, input_path, replace=False, yes=False, keep_previous=False, target_version=None, allow_breaking=False):
    dump = read_dump(input_path)
    collections = preflight(dump, allow_breaking=allow_breaking, target_version=target_version)

    client, db = connect(uri)
    try:
        existing = set(db.list_collection_names())
        leftovers = sorted(n for n in existing if n.startswith((STAGING_PREFIX, PREVIOUS_PREFIX)))
        if leftovers:
            warn(f"{db.name} still has collections from an earlier load: {', '.join(leftovers)}")

        rows = []
        occupied = []
        for name, entry in collections.items():
            current = db[name].count_documents({}) if name in existing else 0
            if current:
                occupied.append(name)
            rows.append((name, entry["count"], current if name in existing else "-"))

        source = dump.get("source") or {}
        local = is_local(uri)
        print(f"Dump:    {input_path}")
        print(f"         from {source.get('database')} at {source.get('uri')}, Locutus {source.get('locutus_version') or 'unknown'}, {dump.get('created_at')}")
        print(f"Target:  {filter_uri(uri)}{'' if local else '  (NOT LOCAL)'}")
        print(f"         database {db.name}\n")
        print_counts(rows, ("Collection", "Incoming", "In target now"))
        print()

        if occupied and not replace:
            raise DbCopyError(
                f"{db.name} already has data in: {', '.join(occupied)}. "
                "Pass --replace to replace those collections (and only those). Nothing was written."
            )

        confirm(db.name, local, yes)

        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        if supports_rename(db, run_id):
            staged = stage(db, collections, run_id)
            previous = swap(db, staged, existing, run_id)
        else:
            warn(f"{db.name} doesn't support renaming collections, so the load runs in place. Recovery relies on the database's own backups.")
            load_in_place(db, collections, existing)
            previous = {}

        if "User" in collections and "User" in existing and "sessions" not in collections and "sessions" in existing:
            cleared = db["sessions"].delete_many({}).deleted_count
            if cleared:
                print(f"Signed out {cleared} session(s), since the User records were replaced.")

        mismatched = []
        for name, entry in collections.items():
            count = db[name].count_documents({})
            if count != entry["count"]:
                mismatched.append(f"{name} has {count}, expected {entry['count']}")
        if mismatched:
            kept = ", ".join(previous.values()) or "none"
            raise DbCopyError(
                "Counts after the load don't match the dump (is something else writing to it?): "
                + "; ".join(mismatched)
                + f". Previous collections kept: {kept}"
            )

        if previous and keep_previous:
            print("Previous collections kept for a manual rollback: " + ", ".join(previous.values()))
        else:
            drop_quietly(db, previous.values())

        print(f"Loaded {sum(e['count'] for e in collections.values())} documents into {db.name}.")
        print("Everyone needs to sign in again: login sessions are never copied.")
    finally:
        client.close()
