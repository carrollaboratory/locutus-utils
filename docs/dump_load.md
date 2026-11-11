# Copying a database

`locutils dump` writes a whole Locutus database to a single JSON file, and
`locutils load` loads that file into another database. The main use is
testing: bring up a local stack with a copy of real data before deploying.
It also works for copying a database between deployments.

The copy is exact. Documents keep their `_id`s, ObjectIds and dates come back
as the same types, and each collection's indexes are recreated.

> **Dumps contain real user emails and the admin list.** Keep them out of
> version control and only share them with people who already have access to
> that data. Dump files are created readable by their owner only.

## Dump

```bash
locutils dump -db "$MONGO_URI" -o backups/dev.locutus.json.gz --source-url https://dev.example.org
```

- `-db` defaults to `$DB_URI`, then `$MONGO_URI`. The URI must name the
  database.
- `-o` is gzipped when it ends in `.gz`. Without `-o` the file goes to
  `backups/<database>-<UTC time>.locutus.json.gz`. An existing file is only
  overwritten with `--force`.
- `--source-url` asks the running Locutus (or Map Dragon) for its release via
  `/api/version` and records it in the dump. Use `--locutus-version v2.3.1`
  to state it instead.
- Login sessions (`sessions`) are never dumped. API tokens (`ApiToken`) are
  skipped unless `--include-tokens` is passed, since anyone who loads the
  dump could then use them.
- Collections this tool doesn't know about are dumped anyway, with a warning.

The file is written to a temporary name and only moved into place once the
whole dump succeeds, so a failed dump never leaves a partial file behind.

Mongo can't snapshot several collections at once, so dump at a quiet moment.
Edits made while the dump runs may be half captured.

## Load

```bash
locutils load -db "$MONGO_URI" -i backups/dev.locutus.json.gz [--replace] [--yes]
```

Before writing anything, the load reads the whole file and checks it: the file
format, the Locutus releases (below), document counts, duplicate `_id`s and
document sizes. It then shows the target and the per-collection counts and
asks you to type the database name. For a database that isn't local, it first
asks you to confirm a recent backup exists. `--yes` skips both prompts.

If any collection in the dump already has data in the target, the load stops.
`--replace` replaces those collections, and only those. Collections in the
target that aren't in the dump are left alone, except that login sessions are
cleared when `User` is replaced.

### All or nothing

The load writes each collection to a staging collection
(`_load_<run>__<name>`) first. Only when everything has been written and
counted does it swap them in: each existing collection is renamed to
`_prev_<run>__<name>` and the staged one takes its name. If anything fails
before or during the swap, the target is put back the way it was. The
`_prev_` collections are dropped at the end, unless `--keep-previous` is
passed to keep them for a manual rollback.

Databases that can't rename collections (Firestore's MongoDB API) are loaded
in place instead. Recovery there relies on the database's own backups.

### Locutus releases

Locutus has no schema version, so loads compare the Locutus release that wrote
the dump with the one serving the target (`--target-url` or
`--target-version`). A different release only produces a warning. A release
that changes stored data incompatibly would be listed in
`locutils/dbcopy/versions.py`, and a load across it is refused unless
`--allow-breaking` is passed. No release is listed today.

After a load everyone needs to sign in again. Admins come from the copied
`Config` and `User` records. Run the seed afterwards with
`--force-admin --no-terminologies --no-api-ontologies` to add your own admin
emails without touching the copied terminologies.

## File format

One JSON object in MongoDB relaxed Extended JSON:

```json
{
  "format": "locutus-dump",
  "format_version": 1,
  "json_mode": "relaxed",
  "created_at": {"$date": "2026-11-11T18:04:11Z"},
  "tool": "locutils 0.3.0",
  "scope": {"kind": "full"},
  "source": {"database": "locutus", "uri": "mongodb://user:****@host/locutus", "locutus_version": "v2.3.1"},
  "collections": {
    "Terminology": {
      "indexes": [{"name": "...", "key": [["field", 1]], "options": {}}],
      "documents": [
        {"_id": {"$oid": "6731..."}, "id": "6731...", "name": "..."}
      ],
      "count": 1
    }
  }
}
```

Documents are sorted by `_id`, one per line, so two dumps of the same data can
be diffed. Passwords are masked in `source.uri`.
