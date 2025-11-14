import importlib_resources
from .. import read_file

_support_details = importlib_resources.files("search_dragon") / "support"

def open_support_file(file_name):
    return read_file(_support_details / filename)
