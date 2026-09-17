import importlib
import re
from pathlib import Path


def valid_email(email_string: str) -> str:
    """Validates email format for argparse."""
    # Standard loose regex pattern covering most common email formats
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    # Clean whitespace just in case of terminal paste artifacts
    cleaned_email = email_string.strip()

    if not re.match(email_pattern, cleaned_email):
        msg = f"Invalid email format: '{email_string}'. Must match 'user@domain.com'."
        raise ArgumentTypeError(msg)

    return cleaned_email


def load_tools():
    tools = {}

    # Anything inside the tools directory that starts with a letter is going
    # to be recognized as a tool, so don't put anything in there named like
    # a tool that doesn't exhibit the tool interface.
    for filename in Path(__file__).absolute().parent.glob("[A-Za-z]*.py"):
        toolname = filename.stem
        tool_lib = importlib.import_module(f"locutils.tools.loctoken.{toolname}")
        tools[tool_lib.__name__] = tool_lib
    return tools
