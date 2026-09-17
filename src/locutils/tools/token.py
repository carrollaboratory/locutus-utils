#!/usr/bin/env python


import logging
import os
from argparse import ArgumentParser

logger = logging.getLogger(__name__)
from .. import init_backend
from .loctoken import load_tools


def db_uri():
    # Support for the Locutus ENV Variable, if it's present
    db_uri = os.getenv("MONGO_URI", None)

    # However, we'll preference the KF teams request, if it is there
    db_uri = os.getenv("DB_URI", db_uri)

    return db_uri


def loctok(arguments: list[str] | None = None):
    from locutils._version import __version__

    defaultdb = db_uri()
    parser = ArgumentParser(description="Load CSV data into locutus database.")
    # cfg_parser.add_argument("--config", type=FileType("r"), default=cfg_args.config)
    parser.add_argument(
        "-db",
        "--db-uri",
        required=defaultdb is None,
        default=defaultdb,
        help="The locutus database URI to be updated.",
    )

    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show application version and exit",
    )
    subparsers = parser.add_subparsers(
        title="command", dest="command", required=True, help="Command to be run"
    )
    tools = load_tools()

    for toolname in tools:
        tools[toolname].add_arguments(subparsers)

    args = parser.parse_args(arguments)

    from locutus.storage.mongo import filter_uri

    print(f"Database URI: {filter_uri(args.db_uri)}")

    client = init_backend(args.db_uri)

    # Now, we run the command the user selected
    tools[args.command].exec(args)
