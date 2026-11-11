"""Copy a Locutus database to a single JSON file and back.

`locutils dump` writes every collection (with its indexes) as MongoDB
Extended JSON, so ObjectIds and dates come back as the same types.
`locutils load` stages the incoming data next to the real collections and
swaps it in only after everything has been written and checked, so a failed
load leaves the target as it was.
"""

import re
import sys

uri_filter = re.compile(r"(mongodb(?:\+srv)?://[^:/@]*:)([^@]*)(@)")

# Login sessions are tied to the source server's random signing key, so
# they are never useful anywhere else.
ALWAYS_SKIP = {"sessions"}

# Token hashes grant API access, so they only travel when asked for.
TOKEN_COLLECTIONS = {"ApiToken"}

# Without these, the copy has no accounts, institutions or admin list.
CORE_COLLECTIONS = ("User", "Institution", "Config")

# Collections the loader creates while it works. Leftovers (from a failure
# or --keep-previous) are never dumped.
STAGING_PREFIX = "_load_"
PREVIOUS_PREFIX = "_prev_"

# Collections Locutus is known to use at the time of writing. Anything else
# is still dumped, just with a warning, so collections added by newer
# releases aren't lost.
KNOWN_COLLECTIONS = {
    "ApiToken",
    "Coding",
    "Config",
    "DataDictionary",
    "GlobalID",
    "Institution",
    "Mapping",
    "MappingConversation",
    "MappingVote",
    "OntologyAPI",
    "Provenance",
    "Study",
    "Table",
    "Terminology",
    "User",
}


class DbCopyError(Exception):
    """A problem that stops a dump or load. The message is shown as is."""


def filter_uri(uri):
    return uri_filter.sub(r"\1****\3", uri)


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


def is_known_collection(name):
    # Nested collections are named Parent__<id>__child
    return name in KNOWN_COLLECTIONS or name.split("__", 1)[0] in KNOWN_COLLECTIONS


def print_counts(rows, headers):
    """Print a plain text table. rows is a list of tuples."""
    rows = [tuple(str(c) for c in r) for r in rows]
    widths = [len(h) for h in headers]
    for r in rows:
        widths = [max(w, len(c)) for w, c in zip(widths, r)]
    line = "  ".join(f"{{:<{w}}}" for w in widths)
    print(line.format(*headers).rstrip())
    print(line.format(*["-" * w for w in widths]).rstrip())
    for r in rows:
        print(line.format(*r).rstrip())
