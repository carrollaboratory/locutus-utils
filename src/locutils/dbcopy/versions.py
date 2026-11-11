"""Locutus release checks for dumps and loads.

Locutus has no schema version, so the check compares the Locutus releases
that wrote the dump and that serve the target. A mismatch only warns, unless
the two releases sit on opposite sides of a release listed in
BREAKING_RELEASES, which means stored data changed incompatibly and a
migration should run first.
"""

import re

import requests

from . import DbCopyError, warn

# Locutus releases that changed stored data in a way older/newer code can't
# read. None so far: the auth work only added collections, and Locutus
# repairs the minor field changes itself when it reads them.
BREAKING_RELEASES: list[str] = []

_release = re.compile(r"^v?(\d+(?:\.\d+)*)")


def parse_release(version):
    """'v2.3.1' or '2.3.1.dev4+gabc' -> (2, 3, 1). None if it isn't a
    release number (e.g. 'local')."""
    if not version:
        return None
    m = _release.match(str(version).strip())
    if not m:
        return None
    return tuple(int(x) for x in m.group(1).split("."))


def fetch_version(base_url):
    """Ask a running Locutus (or Map Dragon, which proxies /api) for its
    release."""
    url = base_url.rstrip("/")
    if not url.endswith("/api"):
        url += "/api"
    url += "/version"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()["version"]
    except Exception as e:  # noqa: BLE001
        raise DbCopyError(f"Unable to read the Locutus version from {url}: {e}")


def resolve_version(url, version, label):
    if url and version:
        raise DbCopyError(f"Give either a {label} URL or a {label} version, not both.")
    if url:
        return fetch_version(url)
    return version


def crossed_breaking_releases(source, target):
    lo, hi = sorted([source, target])
    return [
        b
        for b in BREAKING_RELEASES
        if (p := parse_release(b)) is not None and lo < p <= hi
    ]


def check_versions(source_version, target_version, allow_breaking=False):
    """Warn about mismatches, raise if a breaking release is crossed."""
    source = parse_release(source_version)
    target = parse_release(target_version)

    if source is None or target is None:
        unknown = []
        if source is None:
            unknown.append(f"dump ({source_version or 'not recorded'})")
        if target is None:
            unknown.append(f"target ({target_version or 'not given'})")
        warn(
            "Locutus release unknown for the "
            + " and ".join(unknown)
            + ", so the release check was skipped."
        )
        return

    if source == target:
        return

    crossed = crossed_breaking_releases(source, target)
    if crossed:
        msg = (
            f"The dump was written by Locutus {source_version} and the target "
            f"runs {target_version}. Stored data changed in {', '.join(crossed)}, "
            "so the data should be migrated before loading."
        )
        if not allow_breaking:
            raise DbCopyError(msg + " Pass --allow-breaking to load anyway.")
        warn(msg)
        return

    warn(
        f"The dump was written by Locutus {source_version} and the target runs "
        f"{target_version}. No breaking release lies between them, so loading anyway."
    )
