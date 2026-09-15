import argparse
from pathlib import Path


def readable_file(path_str: str) -> Path:
    """Validate that the path exists and is a file."""
    path = Path(path_str)
    if not path.is_file():
        raise argparse.ArgumentTypeError(
            f"The file '{path_str}' does not exist or is not a file."
        )
    return path
