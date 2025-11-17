import logging
import yaml
import requests
import os
import json
import re
import sys
import time
import pandas as pd
from pathlib import Path
from csv import DictReader 
import io

_loc_client = None
logger = logging.getLogger(__name__)

def init_backend(dburi=None):
    global _loc_client
    if _loc_client is None:
        if dburi is None:
            logger.error("Database URI must be provided before running this script.")
            sys.exit(1)
        from locutus import persistence

        _loc_client = persistence(mongo_uri=dburi, missing_ok=True)
        logger.info(f"Initialing locutus datamodel with db: {dburi}")

    return _loc_client

def get_reader(file_path, delimiter=None):
    if re.search(r'^https:', file_path):
        return get_reader_from_gh(url=file_path, delimiter=delimiter)
    return DictReader(open(file_path, 'rt'))

def get_reader_from_gh(url, delimiter=None):
    "Returns a dictreader iterator"
    resp = requests.get(url)

    return DictReader(io.StringIO(resp.content.decode("utf-8")))

def read_file(filepath,delimeter=None):
    
    file_ext = os.path.splitext(filepath)[-1].lower()

    if not delimeter and file_ext == 'csv':
        delimeter = ","

    # We may want to move the opens into separate functors that do the import
    # inline as opposed to importing all possible options. For now, we'll keep it
    # as is. 
    file_handlers = {
        ".yaml": lambda: yaml.safe_load(open(filepath, "r")),
        ".yml": lambda: yaml.safe_load(open(filepath, "r")),
        ".csv": lambda: pd.read_csv(filepath, header=0, sep=delimeter),
        ".xlsx": lambda: pd.read_excel(filepath, header=0),
        ".sql": Path(filepath).read_text,
        ".json": lambda: json.load(open(filepath, "r")),
        ".owl": lambda: open(filepath, "r", encoding="utf-8").read()  # Read OWL file as plain text
    }

    if file_ext not in file_handlers:
        raise ValueError(f"Unsupported file type: {file_ext}")

    logger.debug(f"Reading {file_ext} from file: {filepath}")

    data = file_handlers[file_ext]()

    logger.debug(f"Read {filepath} successful")
    return data, file_ext

def write_file(filepath, data, sort_by_list=[]):
    """Creates a directory for the table and writes a YAML, SQL, BASH, or Markdown file based on the extension."""
    filepath = Path(filepath)
    file_extension = filepath.suffix

    data = pd.DataFrame(data)
    data = data.sort_values(by=sort_by_list)

    file_handlers = {
        ".csv": lambda: data.to_csv(filepath, index=False),
        ".tsv": lambda: data.to_csv(filepath, sep='\t', index=False)
    }

    if file_extension not in file_handlers:
        raise ValueError(f"Unsupported file type: {file_extension}")
    
    logger.debug(f"Writing {file_extension} to file: {filepath}")
    file_handlers[file_extension]()

    logger.info(f"Generated: {Path(filepath).name}")