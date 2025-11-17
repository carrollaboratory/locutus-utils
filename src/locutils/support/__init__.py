import importlib_resources
from .. import read_file

_support_details = importlib_resources.files("locutils") / "support"

def open_support_file(file_name):
    return read_file(_support_details / file_name)
