"""Argument handling for `locutils dump` and `locutils load`."""

import os
import sys
from argparse import ArgumentParser
from datetime import UTC, datetime

from . import DbCopyError
from .versions import resolve_version


def default_uri():
    # Same lookup as the seed tool: DB_URI wins over Locutus's MONGO_URI
    return os.getenv("DB_URI", os.getenv("MONGO_URI"))


def build_parser(tool_version):
    uri = default_uri()
    parser = ArgumentParser(
        prog="locutils",
        description="Copy a whole Locutus database to a JSON file (dump) and back (load).",
    )
    parser.add_argument("--version", action="version", version=f"locutils {tool_version}")
    sub = parser.add_subparsers(dest="command", required=True)

    dump = sub.add_parser(
        "dump",
        help="Write a database to a dump file",
        description="Write every collection of a Locutus database, with its indexes, to one "
        "JSON file. Login sessions are never included, and API tokens only with "
        "--include-tokens. The file holds real user emails: keep it out of version control.",
    )
    dump.add_argument("-db", "--db-uri", required=uri is None, default=uri,
                      help="Database to dump (default: $DB_URI or $MONGO_URI).")
    dump.add_argument("-o", "--output",
                      help="File to write; gzipped when it ends in .gz "
                      "(default: backups/<database>-<UTC time>.locutus.json.gz).")
    dump.add_argument("--force", action="store_true", help="Overwrite the output file if it exists.")
    dump.add_argument("--include-tokens", action="store_true",
                      help="Include API token hashes. Anyone who loads the dump can then use those tokens.")
    dump.add_argument("--source-url",
                      help="Base URL of the Locutus (or Map Dragon) serving this database, to record its release.")
    dump.add_argument("--locutus-version", help="Locutus release that serves this database, if not using --source-url.")

    load = sub.add_parser(
        "load",
        help="Load a dump file into a database",
        description="Load a full dump. Data is staged and swapped in only once everything is "
        "written, so a failed load leaves the target as it was.",
    )
    load.add_argument("-db", "--db-uri", required=uri is None, default=uri,
                      help="Database to load into (default: $DB_URI or $MONGO_URI).")
    load.add_argument("-i", "--input", required=True, help="Dump file to load.")
    load.add_argument("--replace", action="store_true",
                      help="Replace collections in the dump that already have data in the target.")
    load.add_argument("-y", "--yes", action="store_true", help="Don't ask for confirmation.")
    load.add_argument("--keep-previous", action="store_true",
                      help="Keep the replaced collections as _prev_<run>__<name> for a manual rollback.")
    load.add_argument("--target-url",
                      help="Base URL of the Locutus (or Map Dragon) serving the target, to check releases.")
    load.add_argument("--target-version", help="Locutus release serving the target, if not using --target-url.")
    load.add_argument("--allow-breaking", action="store_true",
                      help="Load even if a breaking Locutus release lies between the dump and the target.")
    return parser


def main(argv=None):
    from locutils._version import __version__

    args = build_parser(__version__).parse_args(argv)
    try:
        if args.command == "dump":
            from .dump import connect, run_dump

            output = args.output
            if output is None:
                client, db = connect(args.db_uri)
                client.close()
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                output = f"backups/{db.name}-{stamp}.locutus.json.gz"
            if os.path.exists(output) and not args.force:
                raise DbCopyError(f"{output} already exists. Pass --force to overwrite it.")
            run_dump(
                args.db_uri,
                output,
                source_version=resolve_version(args.source_url, args.locutus_version, "source"),
                include_tokens=args.include_tokens,
                tool_version=__version__,
            )
        else:
            from .load import run_load

            run_load(
                args.db_uri,
                args.input,
                replace=args.replace,
                yes=args.yes,
                keep_previous=args.keep_previous,
                target_version=resolve_version(args.target_url, args.target_version, "target"),
                allow_breaking=args.allow_breaking,
            )
    except DbCopyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    return 0
