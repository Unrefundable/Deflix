#!/usr/bin/env python3
"""Bring the published Deflix repository's copy of KDMM up to date.

Most devices only read the Deflix directory of the repository (Kodi does not
auto-update a repository add-on that was installed from a zip), so they get
KDMM from the copy that directory carries. This script replaces that copy
with KDMM's current release and touches nothing else: the skin zip and the
other entries of addons.xml stay as published.

It works on a checkout of the gh-pages branch and leaves committing to the
caller; .github/workflows/sync-kdmm.yml runs it on a schedule.

Usage:
  python3 tools/sync_kdmm.py <gh-pages checkout>
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from build_kodi_repo import KDMM_ID, kdmm_release, mirror_kdmm, save_addons_xml, version_tuple


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    repo_dir = Path(sys.argv[1]) / "repository"
    addons = ET.parse(repo_dir / "addons.xml").getroot()
    published = next((a for a in addons.iter("addon") if a.attrib.get("id") == KDMM_ID), None)
    have = published.attrib["version"] if published is not None else "0"

    release = kdmm_release()
    latest = release.attrib["version"]
    if version_tuple(latest) <= version_tuple(have):
        print(f"KDMM {have} is published; KDMM's repository has {latest}. Nothing to do.")
        return

    for old_zip in (repo_dir / KDMM_ID).glob(f"{KDMM_ID}-*.zip"):
        old_zip.unlink()
    mirror_kdmm(release, repo_dir)
    if published is not None:
        addons.remove(published)
    addons.append(release)
    save_addons_xml(addons, repo_dir)
    print(f"KDMM {have} -> {latest}")


if __name__ == "__main__":
    main()
