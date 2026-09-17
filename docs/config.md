# Configuration

Locutus Utils relies on a single configuration YAML file to provide the
information required for determining what to seed. This configuration file is
broken into 3 top level sections:

- organizations
- admin_emails
- institutions
- terminologies

The default filename is "config.yaml", but users can provide any name they wish
using the --config option.

## organizations

This is a simple YAML list and provides each of the different orgazations that
members may be a part of. There should be 1 or more organizations provided. The
organization can be considered to be more closely related to the group for whom
the deployment is intended. For instance, 'kf' might be the designation for the
deployment for the INCLUDE/kf deployment.

the following is an example of an organizations entry:

```yaml
organizations:
  - kf
  - include
  - anvil
```

When locutus runs, it is run with a single organization being active. This
determines which resources are seeded.

## admin_emails

For certain tasks, users are expected to have admin rights. This includes
creating new institutions and adding emails to an institution and granting admin
rights to other uers. For newly provisioned machines, this is done using a
bootstrap list of administrator emails.

Typically, this will only be seeded if the structure is missing altogether to
prevent old emails from getting added back in by accident.

```yaml
admin_emails:
  - email.address@domain.org
  - another.address@domain.org
```

## institutions

At least one Instititution, with at least a single allowed_email is required.
When a user first attempts to log in, their email address is compared to all
institutions present on the given server. If their email address is "allowed",
they are permitted to log in and are granted access to all Institution based
resources. A user may be a member of more than one institution.

It is important that any individuals that may be the first to log in after a
fresh deployment be added as "allowed emails" to any institutions they are
expected to be responsible for. Any user logged in that is currently recognized
as a member of an Institution can add or remove emails and IDs.

The following is an example of an institution entry:

```yaml
institutions:
  vumc:
    name: Vanderbilt Medical Center
    allowed_emails:
      - email.one@vumc.org
      - email.two@vumc.org
    organizations:
      - include
      - kf
      - anvil
  kf:
    name: Kids First
    organizations:
      - kf
    allowed_emails:
```

## Terminologies

The terminology section is a bit more complex. The following example is a good
start and will populate the 2 ontologies that must exist for MapDragon to work
correctly.

```yaml
terminologies:
  concept_map_relationship:
    refresh_or_normalize: False # FTD legacy manually created
    seed_db: True
    organizations:
      - all
    remove_codes: True
    source_data: None # Not being normalized
    normalized_data:
      type: csv
      name:
        - concept_map_relationship.csv
      delimeter: ","
      url_prefix: "https://raw.githubusercontent.com/NIH-NCPI/locutus_utilities/refs/heads/main/data/seed_etl"
  ucum_common_units:
    refresh_or_normalize: False # FTD legacy manually created
    seed_db: True
    organizations:
      - all
    remove_codes: True
    source_data: None # Not being normalized
    normalized_data:
      type: csv
      name:
        - ucum_common_units.csv
      delimeter: ","
      url_prefix: https://raw.githubusercontent.com/NIH-NCPI/locutus_utilities/refs/heads/main/data/seed_etl
```
