"""Reading and writing the dump file.

A dump is one JSON object, gzipped when the file name ends in .gz:

    {
      "format": "locutus-dump",
      "format_version": 1,
      "json_mode": "relaxed",
      "created_at": {"$date": ...},
      "tool": "locutils x.y.z",
      "scope": {"kind": "full"},
      "source": {"database": ..., "uri": <password masked>, "locutus_version": ...},
      "collections": {
        "<name>": {"indexes": [...], "documents": [ ... ], "count": N},
        ...
      }
    }

Documents use relaxed Extended JSON from bson.json_util, so ObjectIds,
dates and other BSON types come back as the same types, while plain
numbers and strings stay readable. Each document sits on its own line and
documents are sorted by _id, so two dumps of the same data can be diffed.
"""

import gzip
import io
import json
import os
from pathlib import Path

from bson import Int64, json_util

from . import DbCopyError

FORMAT = "locutus-dump"
FORMAT_VERSION = 1
JSON_OPTIONS = json_util.RELAXED_JSON_OPTIONS


def _keep_int64(value):
    """Relaxed mode writes a 64-bit int as a plain number, which comes back
    as a 32-bit int when it's small. Spell those out so the type survives."""
    if isinstance(value, Int64):
        return {"$numberLong": str(int(value))}
    if isinstance(value, dict):
        return {k: _keep_int64(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_keep_int64(v) for v in value]
    return value


def to_json(value):
    return json_util.dumps(_keep_int64(value), json_options=JSON_OPTIONS)


class DumpWriter:
    """Streams a dump to a temporary file next to the destination and only
    moves it into place when close() is called after a clean run. Use as a
    context manager: an exception removes the partial file."""

    def __init__(self, path, header):
        self.path = Path(path)
        self.tmp = self.path.with_name(f".{self.path.name}.partial-{os.getpid()}")
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Dumps hold real emails, so keep them readable by the owner only.
        fd = os.open(self.tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        raw = os.fdopen(fd, "wb")
        if self.path.suffix == ".gz":
            # mtime=0 and no embedded name, so the bytes only depend on content
            self._gz = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
            self._raw = raw
            self.out = io.TextIOWrapper(self._gz, encoding="utf-8")
        else:
            self._gz = None
            self._raw = None
            self.out = io.TextIOWrapper(raw, encoding="utf-8")

        self.out.write("{\n")
        for key, value in header.items():
            self.out.write(f"  {json.dumps(key)}: {to_json(value)},\n")
        self.out.write('  "collections": {')
        self._first_collection = True

    def write_collection(self, name, indexes, documents):
        """documents is any iterable; it's consumed one document at a time.
        Returns the number written."""
        sep = "\n" if self._first_collection else ",\n"
        self._first_collection = False
        self.out.write(f"{sep}    {json.dumps(name)}: {{\n")
        self.out.write(f'      "indexes": {to_json(indexes)},\n')
        self.out.write('      "documents": [')
        count = 0
        for doc in documents:
            self.out.write(("\n" if count == 0 else ",\n") + "        " + to_json(doc))
            count += 1
        self.out.write("\n      ],\n" if count else "],\n")
        self.out.write(f'      "count": {count}\n    }}')
        return count

    def close(self):
        self.out.write("\n  }\n}\n")
        self.out.close()
        if self._raw is not None:
            self._raw.close()
        os.replace(self.tmp, self.path)

    def abort(self):
        try:
            self.out.close()
            if self._raw is not None:
                self._raw.close()
        except Exception:  # noqa: BLE001
            pass
        self.tmp.unlink(missing_ok=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.close()
        else:
            self.abort()
        return False


def read_dump(path):
    """Read and parse a whole dump file. Raises DbCopyError for anything
    that isn't a complete, readable dump."""
    path = Path(path)
    if not path.is_file():
        raise DbCopyError(f"{path} does not exist or is not a file.")

    with path.open("rb") as f:
        magic = f.read(2)
    opener = gzip.open if magic == b"\x1f\x8b" else open
    try:
        with opener(path, "rt", encoding="utf-8") as f:
            data = json_util.loads(f.read(), json_options=JSON_OPTIONS)
    except (OSError, EOFError, ValueError) as e:
        raise DbCopyError(f"{path} is not a readable dump (truncated or corrupt?): {e}")

    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise DbCopyError(f"{path} is not a Locutus dump file.")
    return data
