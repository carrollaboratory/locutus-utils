import importlib_resources
from yaml import safe_load

_support_details = importlib_resources.files("locutils") / "support"

def open_support_file(file_name):
    return safe_load(open(_support_details / file_name, "r"))
