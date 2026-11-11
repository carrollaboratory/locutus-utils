"""locutils dump: write a whole Locutus database to one JSON file."""

from datetime import UTC, datetime

from pymongo import ASCENDING, MongoClient
from pymongo.errors import ConfigurationError, PyMongoError

from . import (
    ALWAYS_SKIP,
    CORE_COLLECTIONS,
    PREVIOUS_PREFIX,
    STAGING_PREFIX,
    TOKEN_COLLECTIONS,
    DbCopyError,
    filter_uri,
    is_known_collection,
    print_counts,
    warn,
)
from .dumpfile import FORMAT, FORMAT_VERSION, DumpWriter


def connect(uri):
    """MongoClient plus the database named in the URI. A plain client is
    used rather than Locutus's own, which only exposes the collections it
    knows about."""
    client = MongoClient(uri)
    try:
        db = client.get_default_database()
    except ConfigurationError:
        client.close()
        raise DbCopyError("The database URI must name the database, e.g. mongodb://host/locutus")
    return client, db


def index_specs(collection):
    """Index definitions, minus the automatic _id index, in a form
    create_index() accepts again."""
    try:
        info = collection.index_information()
    except PyMongoError as e:
        warn(f"Unable to read the indexes of {collection.name} ({e}). Locutus rebuilds its own indexes at startup.")
        return []
    specs = []
    for name, spec in sorted(info.items()):
        if name == "_id_":
            continue
        options = {k: v for k, v in spec.items() if k not in ("key", "v", "ns")}
        specs.append({"name": name, "key": [[f, d] for f, d in spec["key"]], "options": options})
    return specs


def choose_collections(names, include_tokens):
    chosen, skipped = [], []
    for name in sorted(names):
        if name.startswith("system."):
            continue
        if name.startswith((STAGING_PREFIX, PREVIOUS_PREFIX)):
            warn(f"Skipping {name}, left behind by an earlier load. Drop it once you no longer need it.")
            skipped.append((name, "loader leftover"))
        elif name in ALWAYS_SKIP:
            skipped.append((name, "login sessions are never copied"))
        elif name in TOKEN_COLLECTIONS and not include_tokens:
            skipped.append((name, "use --include-tokens to copy"))
        else:
            if not is_known_collection(name):
                warn(f"{name} isn't a collection this tool knows about. Dumping it anyway.")
            chosen.append(name)
    return chosen, skipped


def run_dump(uri, output, source_version=None, include_tokens=False, tool_version="unknown"):
    client, db = connect(uri)
    try:
        names = db.list_collection_names()
        chosen, skipped = choose_collections(names, include_tokens)
        if not chosen:
            raise DbCopyError(f"Database {db.name} has no collections to dump. Check the database name in the URI.")

        missing_core = [c for c in CORE_COLLECTIONS if c not in chosen]
        if missing_core:
            warn(f"{db.name} has no {', '.join(missing_core)} collection(s). A copy loaded from this dump won't have accounts or admins.")
        if source_version is None:
            warn("The Locutus release isn't recorded. Pass --source-url or --locutus-version so loads can check it.")

        header = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "json_mode": "relaxed",
            "created_at": datetime.now(UTC).replace(microsecond=0),
            "tool": f"locutils {tool_version}",
            "scope": {"kind": "full"},
            "source": {
                "database": db.name,
                "uri": filter_uri(uri),
                "locutus_version": source_version,
            },
        }

        counts = []
        with DumpWriter(output, header) as writer:
            for name in chosen:
                coll = db[name]
                n = writer.write_collection(name, index_specs(coll), coll.find({}).sort("_id", ASCENDING))
                counts.append((name, n))

        print_counts(counts + [(name, f"skipped: {why}") for name, why in skipped], ("Collection", "Documents"))
        print(f"\nWrote {sum(n for _, n in counts)} documents from {db.name} to {output}")
        print(
            "Reminder: this file holds real user emails and the admin list. "
            "Keep it out of version control and share it only with people who already have access to that data."
        )
    finally:
        client.close()
