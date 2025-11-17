# Seeding the database
locutils can be used to load Terminologies and Ontology API configuration details to a new database or update them within an existing database. The default configuration points to our Locutus Utilities repository where the files are created. However, users can also load terminologies from their local machine (or elsewhere on the web) as long as those files are formatted correctly. 

## Usage
Users can get help directly using the -h flag
```bash
usage: locutils [-h] -db DB_URI [-s {terminologies,ontology_api,all}]
                [-o {kf,include,anvil}] [-a {seed}] [-t TERMINOLOGY_CSV]
                [-api | --api-ontologies | --no-api-ontologies]

Load CSV data into Firestore.

options:
  -h, --help            show this help message and exit
  -db, --db-uri DB_URI  The locutus database URI to be updated.
  -s, --seed-type {terminologies,ontology_api,all}
                        Which types of data do you wish to seed. Default to all types.
  -o, --org {kf,include,anvil}
                        Which organization is this run for? This only impacts 'load
                        default' behavior
  -a, --action {seed}   Which action should be taken.
  -t, --terminology_csv TERMINOLOGY_CSV
                        By default, the contents will be loaded based on the support
                        configuration data built into the library, but users can load
                        arbitrary terminologies as well. This argument may be repeated to
                        load terminologies in multiple files. If one or more are present,
                        the default terminologies are not seeded. Users may provide 'none'
                        as a terminology argument to load only ontology API details.
  -api, --api-ontologies, --no-api-ontologies
                        Load API ontologies (by default).
```

## Important Details
**db-uri** is a required parameter and should follow the mongo convention *mongodb://{user}:{password}@{machinename}:{databasename}* 

**org** is required when using the configuration to load the defaults. This informs the script which ontologies make sense (for example, there may be some ACR specific ontologies that don't make sense for us to load into a KF or INCLUDE hosted instance). 

**api-ontologies** By default, the script will load the API Ontologies. However, if you are just loading some new terminologies or are updating some existing terminologies and don't need to refresh the API Ontology collection, simply turn it off using the flag, --no-api-ontologies. 