import logging
import yaml
import requests
import os
import json
import re
import sys
import time
from pathlib import Path
from csv import DictReader 
import io
from ._version import __version__

if sys.stderr.isatty():
    from rich.console import Console 
    from rich.logging import RichHandler 
    from rich.traceback import install

_loc_client = None
logger = logging.getLogger(__name__)

# Ideally, we should have a readable logger for local execution, but we'll need
# to tweak locutus to do logging a little differently. So, we'll revisit this
# once there is time for doing that little bit of work. 
def init_logging(loglevel):
    global logger
    # When we are in the terminal, let's use the rich logging
    DATEFMT = "%Y-%m-%dT%H:%M:%SZ"
    if sys.stderr.isatty():
        install(show_locals=True)
        
        handler = RichHandler(level=loglevel, 
                console=Console(stderr=True),
                show_time=False,
                show_level=True,
                rich_tracebacks=True)
        FORMAT = "%(message)s"
    else:
        FORMAT = "%(asctime)s\t%(levelname)s\t%(message)s"
        handler = logging.StreamHandler()

    logging.basicConfig(
        level=loglevel, format=FORMAT, datefmt=DATEFMT, handlers=[handler]
    )
    logger = logging.getLogger(__name__)


def init_backend(dburi=None):
    global _loc_client
    if _loc_client is None:
        if dburi is None:
            logger.error("Database URI must be provided before running this script.")
            sys.exit(1)
        from locutus import persistence
        from locutus.storage.mongo import filter_uri

        logger.info(f"Initialing locutus datamodel with db: {filter_uri(dburi)}")
        _loc_client = persistence(mongo_uri=dburi, missing_ok=True)

    return _loc_client

def get_reader(file_path, delimiter=None):
    if re.search(r'^https:', file_path):
        return get_reader_from_gh(url=file_path, delimiter=delimiter)
    return DictReader(open(file_path, 'rt'))

def get_reader_from_gh(url, delimiter=None):
    "Returns a dictreader iterator"
    resp = requests.get(url)

    return DictReader(io.StringIO(resp.content.decode("utf-8")))
