#!/usr/bin/env python3
"""Build the GitHub Pages Kodi repository for Deflix."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import textwrap
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPO_DIR = DOCS / "repository"
PAGES_BASE_URL = "https://unrefundable.github.io/Deflix"
REPOSITORY_ID = "repository.deflix"
REPOSITORY_VERSION = "1.0.0"

EXCLUDED_TOP_LEVEL = {".git", "docs", "tools", "__MACOSX"}
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
    ET.SubElement(extension, "info", {"compressed": "false"}).text = (
        f"{PAGES_BASE_URL}/repository/addons.xml"
    )
    ET.SubElement(extension, "checksum").text = (
        f"{PAGES_BASE_URL}/repository/addons.xml.md5"
    )
    ET.SubElement(extension, "datadir", {"zip": "true"}).text = (
        f"{PAGES_BASE_URL}/repository/"
    )

    metadata = ET.SubElement(addon, "extension", {"point": "xbmc.addon.metadata"})
    ET.SubElement(metadata, "summary", {"lang": "en_GB"}).text = (
        "Install and update the Deflix Kodi skin."
    )
    ET.SubElement(metadata, "description", {"lang": "en_GB"}).text = (
        "Repository for the Deflix Kodi skin."
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


def write_addons_xml(repository_addon: ET.Element) -> Path:
    addons = ET.Element("addons")
    addons.append(ET.parse(ROOT / "addon.xml").getroot())
    addons.append(repository_addon)
    indent_xml(addons)

    target = REPO_DIR / "addons.xml"
    ET.ElementTree(addons).write(target, encoding="utf-8", xml_declaration=True)
    (REPO_DIR / "addons.xml.md5").write_text(md5_file(target), encoding="utf-8")
    return target


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
    write_addons_xml(repository_addon)
    write_page(addon_id, version)

    print(f"Built Deflix {version} Kodi repository in {DOCS}")


if __name__ == "__main__":
    main()
