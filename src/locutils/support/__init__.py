from importlib import resources
from yaml import safe_load

# Python 3.9+ built-in way to access package files
_support_details = resources.files("locutils") / "support"

def open_support_file(file_name):
    # Using the path object directly with a context manager is safer
    with (_support_details / file_name).open("r") as f:
        return safe_load(f)
