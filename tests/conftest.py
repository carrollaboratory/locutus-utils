"""Shared fixtures for the dump/load tests.

Tests marked `mongo` need a MongoDB server. They use
LOCUTILS_TEST_MONGO_URI (default mongodb://127.0.0.1:27017/), which should
name a server but no database. Each test works in its own throwaway
databases (locutils_test_*) and drops them afterwards, so pointing this at
the mapdragon-unified mongo service is safe. When no server answers, those
tests are skipped.
"""

import os
import uuid

import bson
import pytest
from pymongo import MongoClient
from pymongo.errors import PyMongoError

DEFAULT_URI = "mongodb://127.0.0.1:27017/"


def server_uri():
    return os.environ.get("LOCUTILS_TEST_MONGO_URI", DEFAULT_URI)


def with_database(uri, name):
    """Put a database name into a server URI, keeping any options."""
    base, sep, query = uri.partition("?")
    scheme, _, rest = base.partition("://")
    hosts = rest.split("/", 1)[0]
    return f"{scheme}://{hosts}/{name}{sep}{query}"


@pytest.fixture(scope="session")
def mongo_client():
    client = MongoClient(server_uri(), serverSelectionTimeoutMS=2000)
    try:
        client.admin.command("ping")
    except PyMongoError as e:
        client.close()
        pytest.skip(f"No MongoDB at LOCUTILS_TEST_MONGO_URI ({e.__class__.__name__})")
    yield client
    client.close()


@pytest.fixture
def scratch_db(mongo_client):
    """Factory for throwaway databases: returns (uri, db). All of them are
    dropped when the test ends."""
    names = []

    def make():
        name = f"locutils_test_{uuid.uuid4().hex[:12]}"
        names.append(name)
        mongo_client.drop_database(name)
        return with_database(server_uri(), name), mongo_client[name]

    yield make
    for name in names:
        mongo_client.drop_database(name)


def snapshot(db):
    """Every collection's documents as raw BSON, so a comparison catches
    type changes (Int64 vs int, etc.), not just value changes."""
    return {
        name: [bson.encode(d) for d in db[name].find().sort("_id")]
        for name in sorted(db.list_collection_names())
    }
