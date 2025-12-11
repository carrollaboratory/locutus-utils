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
import os 

# Force the Logging Level since Locutus is likely to get that set
# up before CLI has determined what the user might prefer
os.environ['LOCUTUS_LOGLEVEL']='INFO'
from .. import init_backend, get_reader, init_logging
from argparse import ArgumentParser, BooleanOptionalAction, FileType
from ..support import open_support_file
import os
from pathlib import Path
from copy import deepcopy
import logging

# We will want to move this elsewhere eventually, but right now, this is fine,
# since we don't expect it to change. 
ongology_api_metadata = "https://github.com/NIH-NCPI/locutus_utilities/blob/main/data/output/ontology_api_metadata.csv"

# These aren't present inside the CSV data, so we'll just facilitate it here. 
api_metadata = {
    "umls": {
        "name": "UMLS - Unified Medical Language System",
        "url": "https://uts-ws.nlm.nih.gov/rest/"
    },
    "ols": {
        "name": "Ontology Lookup Service",
        "url": "https://www.ebi.ac.uk/ols4/api/"
    }
}

logger = None

class PotentialOrphanedCodings(Exception):
    pass

def db_uri():
    # Support for the Locutus ENV Variable, if it's present
    db_uri = os.getenv("MONGO_URI", None)

    # However, we'll preference the KF teams request, if it is there
    db_uri = os.getenv("DB_URI", db_uri)

    return db_uri

def load_ontology_api_data(db, file_content):
    """Load data from a CSV file and build out the JSON necessary for loading 
    into the database

    Args:
        db - mongodb client object
        file_content - DictReader ready for iteration
    """
    # We don't currently have any use for editor here...
    onto_apis = {}

    for row in file_content:
        if row['api_id'] not in onto_apis:
            onto_apis[row['api_id']] = {
                "api_id": row['api_id'],
                "api_name": api_metadata[row['api_id']]['name'],
                "api_url": api_metadata[row['api_id']]['url'],
                "ontologies": {}
            }
        onto_apis[row['api_id']]['ontologies'][row['curie']] = {
            "version": row.get('verson'),
            "ontology_title": row['ontology_title'],
            "system": row['system'],
            "curie": row['curie'],
            "ontology_code": row['curie'].lower(),
            "short_list": row['short_list'] == "True"
        }
    
    collection = db['OntologyAPI']

    for api, ontology_api in onto_apis.items():
        # Insert/replace the ontology APIs for the given API
        collection.replace_one({
            "api_id": api
        }, ontology_api, upsert=True)
        logger.debug(f"Loaded {len(ontology_api['ontologies'])} for {api}")

def seed_terminology(terminology_data, editor=None):
    """Add terminology to the database using the locutus Model classes

    Args:
      terminology_data (dict): This is a full representation of the terminology
      editor (string): how will the addition be tagged in provenance
    """
    from locutus.model.terminology import Terminology
    term_data = deepcopy(terminology_data)

    if editor is None:
        term_data['editor'] = 'seed-script'

    logger.debug(f"Saving {term_data['name']} ({term_data['id']}) to database with {len(term_data['codes'])}.")

    # Let's confirm that there is nothing to be worried about if we are
    # replacing an existing terminology. 
    tid = term_data.get("id")
    if tid:
        incoming_codes = set([coding['code'] for coding in term_data['codes']])

        orig_term = Terminology.get(tid)
        if orig_term:
            orig_term = orig_term.realize_as_dict()
            existing_codes = set([coding['code'] for coding in orig_term['codes']])

            orphans = existing_codes.difference(incoming_codes)
            if len(orphans):
                raise PotentialOrphanedCodings(f"Terminology, {tid}, exists in the database and has the following Codings that will be orphaned (not replaced) by this operation. {','.join(list(orphans))}")

    # Term is automatically saved when an editor is present in order to capture
    # provenance. So, no need to save here. 
    term = Terminology(**term_data)

def format_for_loc(file_path):
    """Build out the terminology object as expected by the Terminology constructor

    Args:
      file_path (str): GH Source path. We'll pull this down and load it 
                       from file or directly from the web, if it's a web location.
    """
    terminology_data = {}

    reader = get_reader(file_path)
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

def load_default_terminologies(organization):
    term_config = open_support_file("terminologies.yaml")

    terms_seeded = {}
    for file_name, file_config in term_config.items():
        orgs = set([x.lower() for x in file_config.get("organizations")])
        if "all" in orgs or organization.lower() in orgs:
            if file_config.get('seed_db', False) == True: 
                fnames = file_config.get("normalized_data").get('name')

                for file in fnames:
                    logger.debug(f"Reading config settings for file: {file_name}")
                    url_prefix = file_config.get('normalized_data')['url_prefix']
                    filepath = f"{url_prefix}/{file}"

                    term_data = format_for_loc(filepath)
                    for termid, terminology in term_data.items():
                        seed_terminology(terminology)
                        terms_seeded[termid] = terminology
                    logger.debug(f"Adding {file_name}:{file} for loading into database")
        else:
            logger.debug(f"Skipping {file_name}: {organization} not in {','.join(orgs)}")

    return terms_seeded

def locutils():
    from locutils._version import __version__
    global logger

    defaultdb = db_uri()

    parser = ArgumentParser(description="Load CSV data into locutus database.")
    parser.add_argument(
        "-db",
        "--db-uri", 
        required=defaultdb is None,
        default=defaultdb,
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
        "-o",
        "--org",
        choices=['kf', 'include', 'anvil'],
        default='kf',
        help="Which organization is this run for? This only impacts 'load default' behavior"
    )
    parser.add_argument(
        "-a", 
        "--action",
        default="seed",
        choices=['seed'],       # Eventually, there will be others
        help=f"Which action should be taken."
    )
    parser.add_argument(
        "--version",
        action='version',
        version=f'locutils {__version__}',
        help="Print library's version"
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
          "present, the default terminologies are not seeded. "
          ""
          "Users may provide 'none' as a terminology argument to load only "
          "ontology API details. "
    )
    parser.add_argument(
        "-api", 
        "--api-ontologies",
        action=BooleanOptionalAction,
        default=True,
        help="Load API ontologies (by default)."
    )
    # Locutus currently clobbers the logger if we define it here, so I'll leave 
    # this here but comment it out until I have time to update the model to be
    # more flexible. 
    """
    parser.add_argument(
        "-log",
        "--log-level", 
        choices=["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level tolerated (default is INFO)"
    )
    """

    args = parser.parse_args()

    # Holding this off until I've had time to update the model's logging
    # to be more flexible

    # init_logging(args.log_level)
    logger = logging.getLogger(__name__)
    # logger.info(f"Logger initialized to {args.log_level}")
    

    # Initialize the model's database client
    client = init_backend(args.db_uri)

    terms_seeded = {}
    # Load default terminologies if none are provided
    if len(args.terminology_csv) == 0:
        terms_seeded = load_default_terminologies(organization=args.org)
    # Otherwise, load whichever terminologies were specifically provided
    # Users can skip loading terminologies altogether using 'none' as
    # the terminology filename
    elif args.terminology_csv != ['none']: 
        for termcsv in args.terminology_csv:
            term_data = format_for_loc(termcsv.name)
            
            for termid, terminology in term_data.items():
                seed_terminology(terminology)
                terms_seeded[termid] = terminology

    if len(terms_seeded) > 0:
        logger.info(f"Loaded {len(terms_seeded)} terminologies.")
    
        for id, terminology in terms_seeded.items():
            logger.info(f"{id} - {terminology['name']} with {len(terminology['codes'])} codes")

    # Load Ontology API data
    if args.api_ontologies:
        logger.debug(f"Loading API Ontologies")
        csv_content = get_reader("https://raw.githubusercontent.com/NIH-NCPI/locutus_utilities/refs/heads/main/data/output/ontology_api_metadata.csv")
        load_ontology_api_data(client.db, csv_content)