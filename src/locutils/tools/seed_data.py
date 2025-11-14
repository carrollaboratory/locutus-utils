#!/usr/bin/env python

"""

Seed locutus database with new or updated versions of terminologies and 
ontology API configurations. 

For more information, see /locutus_util/seed_etl/README

Run examples
`python seed_etl/seed_database.py`
Options: 
-e change the baseurl from localhost to another url
-a change the default action from seeding the db to deleting from the db.

"""

from .. import read_file, init_backend
from locutus.model.terminology import Terminology
from argparser import ArgumentParser
from ..support import open_support_file

class PotentialOrphanedCodings(Exception):
    pass

def seed_terminology(terminology_data, editor=None):
    term_data = deep_copy(terminology_data)

    if editor is None:
        term_data['editor'] = 'seed-script'

    logger.debug(f"Saving {term_data['name']} ({term_data['id']}) to database.")
    logger.info(term_data)

    # Let's confirm that there is nothing to be worried about if we are
    # replacing an existing terminology. 
    tid = terminology_data.get("id")
    if tid:
        incoming_codes = set([coding.code for coding in terminology_data['codes']])

        orig_term = Terminology.get(tid).realize_as_dict()
        existing_codes = set([coding.code for coding in orig_term['codes']])

        orphans = existing_codes.difference(incoming_codes)
        if len(orphans):
            raise PotentialOrphanedCodings(f"Terminology, {tid}, exists in the database and has the following Codings that will be orphaned (not replaced) by this operation. {','.join(list(orphans))}")

    term = Terminology(terminology_data)
    # Term is automatically saved when an editor is present in order to capture
    # provenance. So, no need to save here. 

def format_for_loc(file_path):
    terminology_data = {}

    with open(file_path, mode="r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            terminology_id = row["terminology_id"]
            if terminology_id not in terminology_data:
                terminology_data[terminology_id] = {
                    "id": row["terminology_id"],
                    "description": row["terminology_description"],
                    "name": row["terminology_name"],
                    "url": row["system"],
                    "resource_type": row["terminology_resource_type"],
                    "codes": [],
                }
            terminology_data[terminology_id]["codes"].append(
                {
                    "code": row["code"],
                    "display": row["display"],
                    "description": row["description"],
                    "system": row['system']
                }
            )
    return terminology_data

def load_default_terminologies():
    term_config, ext = open_support_file("terminologies.yaml")

    terms_seeded = {}
    for file_name, file_config in config.items():
        if file_config.get('seed_db', False) == True: 
            fnames = file_config.get("normalized_data").get('name')

            for file in fnames:
                logger.debug(f"Reading config settings for file: {file_name}")
                filepath = Path("terminologies") / file

            term_data = format_for_loc(filepath)
            for termid, terminology in term_data.items():
                seed_terminology(terminology)
                terms_seeded[termid] = terminology

    return terms_seeded

def seed_database():
    parser = argparse.ArgumentParser(description="Load CSV data into Firestore.")
    parser.add_argument(
        "-db",
        "--db-uri", 
        required=True,
        help="The locutus database URI to be updated."
    )
    parser.add_argument(
        "-s",
        "--seed-type",
        choices=['terminologies', 'ontology_api', 'all'],
        default='all',
        help="Which types of data do you wish to seed. Default to all types."
    )
    parser.add_argument(
        "-a", 
        "--action",
        default="seed",
        choices=['seed'],       # Eventually, there will be others
        help=f"Which action should be taken."
    )
    parser.add_argument(
        "-t", 
        "--terminology_csv",
        default=[],
        type=FileType('rt'),
        action='append',
        help="By default, the contents will be loaded based on the support "
          "configuration data built into the library, but users can load "
          "arbitrary terminologies as well. This argument may be repeated "
          "to load terminologies in multiple files. If one or more are "
          "present, the default terminologies are not seeded."
    )

    args = parser.parse_args()

    # Initialize the model's database client
    client = init_backend(args.db_uri)

    terms_seeded = {}
    # Load default terminologies if none are provided
    if len(args.terminology_csv) == 0:
        terms_seeded = load_default_terminologies()
    else: 
        for termcsv in args.terminology_csv:
            term_data = format_for_loc(termcsv.name)
            
            for termid, terminology in term_data.items():
                seed_terminology(terminology)
                terms_seeded[termid] = terminology

    print(f"Loaded {len(terms_seeded)} terminologies.")
    for id, terminology in terms_seeded.items():
        print(f"{id} - {terminology['name']} with {len(terminology['codes'])} codes")

