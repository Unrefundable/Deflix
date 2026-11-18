#!/usr/bin/env python3
"""Build the GitHub Pages Kodi repository for Deflix."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import textwrap
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPO_DIR = DOCS / "repository"
PAGES_BASE_URL = "https://unrefundable.github.io/Deflix"
REPOSITORY_ID = "repository.deflix"
REPOSITORY_VERSION = "1.0.3"

# The skin depends on add-ons that only the Bingie repository publishes
# (script.bingie.*, plugin.video.tmdb.bingie.helper, ...). Kodi resolves an
# add-on's dependencies from the repository it was installed from, then from
# the official one, so the Deflix repository lists the Bingie directory as a
# second source. Installing Deflix from this repository then pulls everything
# in without the Bingie repository or skin being installed first.
BINGIE_BASE_URL = "https://raw.githubusercontent.com/matke-84/repository.bingie/main/omega"
BINGIE_MIN_KODI = "20.9.1"

# KDMM plays what the skin lists, so the skin depends on it and this repository
# provides it twice over:
#   - as a third directory, KDMM's own repository, so devices get every new
#     KDMM release without Deflix being republished;
#   - as a copy of the current release in the Deflix directory itself, so
#     devices that still have an older repository.deflix (which only knows the
#     Deflix directory) can resolve the dependency when the skin updates.
# Set KDMM_DOCS to a local checkout's docs/ folder to build against a KDMM
# release that is not published yet.
KDMM_ID = "plugin.video.kdmm"
KDMM_BASE_URL = "https://unrefundable.github.io/kdmm"
KDMM_MIN_KODI = "20.9.1"

EXCLUDED_TOP_LEVEL = {
    ".git", ".github", ".claude", "docs", "tools", "__MACOSX",
    "AGENTS.md", "CLAUDE.md",
}
EXCLUDED_NAMES = {".DS_Store"}


def indent_xml(elem: ET.Element) -> None:
    ET.indent(elem, space="    ")


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_skin_metadata() -> tuple[str, str, str]:
    root = ET.parse(ROOT / "addon.xml").getroot()
    return root.attrib["id"], root.attrib["name"], root.attrib["version"]


def should_package(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if rel.parts[0] in EXCLUDED_TOP_LEVEL:
        return False
    if path.name in EXCLUDED_NAMES or path.name.startswith("._"):
        return False
    return path.is_file()


def zip_skin(addon_id: str, version: str) -> Path:
    target_dir = REPO_DIR / addon_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{addon_id}-{version}.zip"

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not should_package(path):
                continue
            archive.write(path, Path(addon_id) / path.relative_to(ROOT))
    return target


def repository_addon_xml() -> ET.Element:
    addon = ET.Element(
        "addon",
        {
            "id": REPOSITORY_ID,
            "version": REPOSITORY_VERSION,
            "name": "Deflix Repository",
            "provider-name": "Unrefundable",
        },
    )
    requires = ET.SubElement(addon, "requires")
    ET.SubElement(requires, "import", {"addon": "xbmc.addon", "version": "12.0.0"})

    extension = ET.SubElement(
        addon,
        "extension",
        {"point": "xbmc.addon.repository", "name": "Deflix Repository"},
    )
    directory = ET.SubElement(extension, "dir")
    ET.SubElement(directory, "info", {"compressed": "false"}).text = (
        f"{PAGES_BASE_URL}/repository/addons.xml"
    )
    ET.SubElement(directory, "checksum").text = (
        f"{PAGES_BASE_URL}/repository/addons.xml.md5"
    )
    ET.SubElement(directory, "datadir", {"zip": "true"}).text = (
        f"{PAGES_BASE_URL}/repository/"
    )

    bingie = ET.SubElement(extension, "dir", {"minversion": BINGIE_MIN_KODI})
    ET.SubElement(bingie, "info", {"compressed": "false"}).text = (
        f"{BINGIE_BASE_URL}/addons.xml"
    )
    ET.SubElement(bingie, "checksum").text = f"{BINGIE_BASE_URL}/addons.xml.md5"
    ET.SubElement(bingie, "datadir", {"zip": "true"}).text = f"{BINGIE_BASE_URL}/"

    kdmm = ET.SubElement(extension, "dir", {"minversion": KDMM_MIN_KODI})
    ET.SubElement(kdmm, "info", {"compressed": "false"}).text = (
        f"{KDMM_BASE_URL}/addons.xml"
    )
    ET.SubElement(kdmm, "checksum").text = f"{KDMM_BASE_URL}/addons.xml.md5"
    ET.SubElement(kdmm, "datadir", {"zip": "true"}).text = f"{KDMM_BASE_URL}/"

    metadata = ET.SubElement(addon, "extension", {"point": "xbmc.addon.metadata"})
    ET.SubElement(metadata, "summary", {"lang": "en_GB"}).text = (
        "Install and update the Deflix Kodi skin."
    )
    ET.SubElement(metadata, "description", {"lang": "en_GB"}).text = (
"Repository for the Deflix Kodi skin and the add-ons it depends on, "
        "including the KDMM player."
    )
    ET.SubElement(metadata, "platform").text = "all"
    assets = ET.SubElement(metadata, "assets")
    ET.SubElement(assets, "icon").text = "icon.png"
    ET.SubElement(assets, "fanart").text = "fanart.jpg"
    return addon


def zip_repository_addon(addon_xml: ET.Element) -> Path:
    target_dir = REPO_DIR / REPOSITORY_ID
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{REPOSITORY_ID}-{REPOSITORY_VERSION}.zip"

    stale_zips = [
        *target_dir.glob(f"{REPOSITORY_ID}-*.zip"),
        *DOCS.glob(f"{REPOSITORY_ID}-*.zip"),
    ]
    for stale_zip in stale_zips:
        stale_zip.unlink()

    with tempfile.TemporaryDirectory() as tmp:
        package_root = Path(tmp) / REPOSITORY_ID
        package_root.mkdir()
        indent_xml(addon_xml)
        ET.ElementTree(addon_xml).write(
            package_root / "addon.xml", encoding="utf-8", xml_declaration=True
        )
        shutil.copy2(ROOT / "resources" / "icon.png", package_root / "icon.png")
        shutil.copy2(ROOT / "resources" / "fanart.jpg", package_root / "fanart.jpg")

        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package_root.rglob("*")):
                archive.write(path, path.relative_to(Path(tmp)))
    shutil.copy2(target, DOCS / target.name)
    return target


def read_kdmm(relative: str) -> bytes:
    """A file of KDMM's published repository, or of a local copy of it."""
    local = os.environ.get("KDMM_DOCS")
    if local:
        return (Path(local) / relative).read_bytes()
    with urllib.request.urlopen(f"{KDMM_BASE_URL}/{relative}", timeout=60) as response:
        return response.read()


def kdmm_release() -> ET.Element:
    """The entry of KDMM's current release in its own repository."""
    for addon in ET.fromstring(read_kdmm("addons.xml")).iter("addon"):
        if addon.attrib.get("id") == KDMM_ID:
            return addon
    raise SystemExit(f"{KDMM_ID} is not listed in KDMM's addons.xml")


def mirror_kdmm(addon: ET.Element, repo_dir: Path = REPO_DIR) -> ET.Element:
    """Copy that KDMM release into a Deflix repository directory; return its entry."""
    version = addon.attrib["version"]
    target_dir = repo_dir / KDMM_ID
    target_dir.mkdir(parents=True, exist_ok=True)
    files = [f"{KDMM_ID}-{version}.zip"]
    files += [asset.text for asset in addon.iter("icon") if asset.text]
    for name in files:
        target = target_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_kdmm(f"{KDMM_ID}/{name}"))

    with zipfile.ZipFile(target_dir / files[0]) as archive:
        packaged = ET.fromstring(archive.read(f"{KDMM_ID}/addon.xml"))
    if packaged.attrib.get("version") != version:
        raise SystemExit(f"KDMM zip is {packaged.attrib.get('version')}, addons.xml says {version}")
    return addon


def required_version(addon_id: str) -> str:
    for required in ET.parse(ROOT / "addon.xml").getroot().iter("import"):
        if required.attrib.get("addon") == addon_id:
            return required.attrib.get("version", "0")
    raise SystemExit(f"addon.xml does not require {addon_id}")


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def save_addons_xml(addons: ET.Element, repo_dir: Path = REPO_DIR) -> Path:
    """Write addons.xml and its checksum the way Kodi expects to read them."""
    indent_xml(addons)
    target = repo_dir / "addons.xml"
    ET.ElementTree(addons).write(target, encoding="utf-8", xml_declaration=True)
    (repo_dir / "addons.xml.md5").write_text(md5_file(target), encoding="utf-8")
    return target


def write_addons_xml(repository_addon: ET.Element, kdmm_addon: ET.Element) -> Path:
    addons = ET.Element("addons")
    addons.append(ET.parse(ROOT / "addon.xml").getroot())
    addons.append(repository_addon)
    addons.append(kdmm_addon)
    return save_addons_xml(addons)


def write_page(addon_id: str, version: str) -> None:
    skin_zip = f"repository/{addon_id}/{addon_id}-{version}.zip"
    repo_zip = f"{REPOSITORY_ID}-{REPOSITORY_VERSION}.zip"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Deflix for Kodi</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #08090b;
      --panel: #14161b;
      --text: #f4f4f5;
      --muted: #b8bcc7;
      --accent: #e50914;
      --line: #2a2d35;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at 20% 0%, #241113 0, transparent 34rem), var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    main {{
      width: min(960px, calc(100% - 40px));
      margin: 0 auto;
      padding: 72px 0;
    }}
    .hero {{
      padding: 36px 0 28px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: clamp(44px, 7vw, 78px);
      line-height: 0.95;
      letter-spacing: 0;
    }}
    p {{ color: var(--muted); max-width: 680px; }}
    a {{ color: var(--text); }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 28px;
    }}
    .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 0 18px;
      border-radius: 6px;
      background: var(--accent);
      color: white;
      text-decoration: none;
      font-weight: 700;
    }}
    .button.secondary {{
      background: #20232a;
      border: 1px solid var(--line);
    }}
    section {{ padding: 28px 0; border-bottom: 1px solid var(--line); }}
    h2 {{ margin: 0 0 14px; font-size: 24px; }}
    ol {{ padding-left: 22px; color: var(--muted); }}
    li {{ margin: 10px 0; }}
    code {{
      display: inline-block;
      max-width: 100%;
      padding: 2px 6px;
      border-radius: 5px;
      background: #20232a;
      color: #fff;
      overflow-wrap: anywhere;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .tile {{
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .tile strong {{ display: block; margin-bottom: 6px; }}
    footer {{ padding-top: 28px; color: var(--muted); font-size: 14px; }}
  </style>
</head>
<body>
  <main>
    <div class="hero">
      <h1>Deflix</h1>
      <p>A Kodi skin with a streaming-focused layout. Install the repository once, then install and update Deflix from Kodi's add-on browser.</p>
      <div class="actions">
        <a class="button" href="{repo_zip}">Download repository zip</a>
        <a class="button secondary" href="{skin_zip}">Download skin zip</a>
      </div>
    </div>

    <section>
      <h2>Kodi Install</h2>
      <ol>
        <li>In Kodi, enable <strong>Unknown sources</strong> under Settings > System > Add-ons.</li>
        <li>Add this file source: <code>{PAGES_BASE_URL}/</code></li>
        <li>Open Add-ons > Install from zip file, choose the source, then install <code>{repo_zip}</code>.</li>
        <li>Open Install from repository > Deflix Repository > Look and feel > Skin > Deflix.</li>
      </ol>
    </section>

    <section>
      <h2>Repository Files</h2>
      <div class="grid">
        <div class="tile">
          <strong>Kodi repository</strong>
          <a href="repository/addons.xml">addons.xml</a>
        </div>
        <div class="tile">
          <strong>Repository installer</strong>
          <a href="{repo_zip}">{repo_zip}</a>
        </div>
        <div class="tile">
          <strong>Current skin package</strong>
          <a href="{skin_zip}">Deflix {version}</a>
        </div>
      </div>
    </section>

    <footer>
      Deflix {version}. Hosted from GitHub Pages.
    </footer>
  </main>
</body>
</html>
"""
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")


def main() -> None:
    addon_id, _name, version = read_skin_metadata()
    if REPO_DIR.exists():
        shutil.rmtree(REPO_DIR)
    REPO_DIR.mkdir(parents=True)

    zip_skin(addon_id, version)
    repository_addon = repository_addon_xml()
    zip_repository_addon(repository_addon)
    kdmm_addon = mirror_kdmm(kdmm_release())
    kdmm_version, kdmm_needed = kdmm_addon.attrib["version"], required_version(KDMM_ID)
    if version_tuple(kdmm_version) < version_tuple(kdmm_needed):
        raise SystemExit(
            f"The skin requires KDMM {kdmm_needed} but KDMM's repository has {kdmm_version}. "
            "Publish KDMM first, or point KDMM_DOCS at its docs/ folder."
        )
    write_addons_xml(repository_addon, kdmm_addon)
    write_page(addon_id, version)

    print(f"Built Deflix {version} Kodi repository in {DOCS} (with KDMM {kdmm_version})")


if __name__ == "__main__":
    main()
