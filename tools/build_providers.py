#!/usr/bin/env python3
"""Generate the streaming-provider hubs for the Deflix skin.

Writes, from the tables below:
  1080i/IncludesProviders.xml       one path variable per provider row
  shortcuts/<provider>hub.DATA.xml  the default rows of each provider hub
  shortcuts/overrides.xml           each row's default style (between the
                                    "provider row styles" markers)

Every row is a TMDb Discover list filtered to one streaming provider in the
viewer's region, served by plugin.video.tmdb.bingie.helper. To add a provider
or a row, edit PROVIDERS or ROWS and run this script again.

Usage:
  python3 tools/build_providers.py
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
HELPER = "plugin://plugin.video.tmdb.bingie.helper/"

# TMDb returns 20 titles per page, so 5 pages make a "Top 100". The other rows
# stay at one page: every title costs the helper a details request, and several
# hundred at once gets it rate-limited by TMDb (HTTP 429), leaving rows empty.
TOP = {"sort_by": "popularity.desc", "length": 5, "limit": 100}
ONE_PAGE = {"limit": 20}
NEW_MOVIES = {"sort_by": "primary_release_date.desc", "primary_release_date.lte": "t-0", "vote_count.gte": 20, **ONE_PAGE}
NEW_SHOWS = {"sort_by": "first_air_date.desc", "first_air_date.lte": "t-0", "vote_count.gte": 20, **ONE_PAGE}


def genre(genre_id: int) -> dict:
    return {"sort_by": "popularity.desc", "with_genres": genre_id, "vote_count.gte": 50, **ONE_PAGE}


def network(network_id: int) -> dict:
    return {"sort_by": "popularity.desc", "with_networks": network_id, **ONE_PAGE}


def studio(company_id: int) -> dict:
    return {"sort_by": "popularity.desc", "with_companies": company_id, **ONE_PAGE}


# Rows every provider can show: key -> (label string id, TMDb type, Discover parameters)
ROWS = {
    "Top100Movies": (31584, "movie", TOP),
    "Top100Shows": (31585, "tv", TOP),
    "NewMovies": (31586, "movie", NEW_MOVIES),
    "NewShows": (31587, "tv", NEW_SHOWS),
    "ActionMovies": (31588, "movie", genre(28)),
    "ComedyMovies": (31589, "movie", genre(35)),
    "DramaShows": (31593, "tv", genre(18)),
    "SciFiFantasyShows": (31594, "tv", genre(10765)),
    "AnimationMovies": (31590, "movie", genre(16)),
    "FamilyMovies": (31591, "movie", genre(10751)),
    "Documentaries": (31592, "movie", genre(99)),
}

# Row styles (see 1080i/IncludesRowStyles.xml). None follows the skin's global widget style.
RANKED, LARGE, LANDSCAPE, POSTER, DEFAULT = "ranked", "large", "landscape", "poster", None


def originals(network_id: int) -> tuple:
    """The provider's own series, as an extra row."""
    return ("Originals", LARGE, (31606, "tv", network(network_id)))


def rows(first: list, genre_style) -> list:
    """`first` rows in the given order and styles, then the genre rows in one style."""
    return first + [(key, genre_style) for key in ROWS if key not in {row[0] for row in first}]


# key: (hub group, TMDb watch-provider id, media type of the spotlight, rows)
# A row is (key from ROWS, style) or (own key, style, (label id, TMDb type, parameters)).
PROVIDERS = {
    "Prime": ("primehub", 9, "tv", rows([
        ("Top100Movies", RANKED), ("Top100Shows", RANKED), originals(1024),
        ("NewMovies", LANDSCAPE), ("NewShows", LANDSCAPE)], LANDSCAPE)),
    "Netflix": ("netflixhub", 8, "tv", rows([
        ("Top100Shows", RANKED), ("Top100Movies", RANKED), originals(213),
        ("NewShows", DEFAULT), ("NewMovies", DEFAULT)], DEFAULT)),
    "AppleTV": ("appletvhub", 350, "tv", rows([
        originals(2552), ("Top100Shows", RANKED), ("Top100Movies", RANKED),
        ("NewMovies", LARGE), ("NewShows", LANDSCAPE)], LANDSCAPE)),
    "Disney": ("disneyhub", 337, "movie", rows([
        ("Disney", LARGE, (31607, "movie", studio(2))),
        ("Pixar", LANDSCAPE, (31608, "movie", studio(3))),
        ("Marvel", LANDSCAPE, (31609, "movie", studio(420))),
        # Lucasfilm (label 31610). The key stays "StarWars" so rows that users have
        # already customised keep pointing at an existing path variable.
        ("StarWars", LANDSCAPE, (31610, "movie", studio(1))),
        ("NationalGeographic", LANDSCAPE, (31611, "movie", studio(7521))),
        ("Top100Movies", RANKED), ("Top100Shows", RANKED),
        ("NewMovies", POSTER), ("NewShows", POSTER)], POSTER)),
}

SPOTLIGHT = {"sort_by": "popularity.desc", "vote_count.gte": 50, "limit": 5}


def discover_path(provider_id: int, tmdb_type: str, params: dict) -> str:
    query = {
        "info": "discover",
        "tmdb_type": tmdb_type,
        "with_watch_providers": provider_id,
        "watch_region": "$VAR[Provider_Region]",
        "with_watch_monetization_types": "flatrate",
        "with_id": "True",
        **params,
        "nextpage": "false",
        "widget": "true",
    }
    return HELPER + "?" + "&".join(f"{key}={value}" for key, value in query.items())


def variable(name: str, value: str) -> str:
    return f'\t<variable name="{name}">\n\t\t<value>{escape(value)}</value>\n\t</variable>\n'


def provider_rows(key: str) -> list:
    """(variable suffix, style, label id, TMDb type, parameters) for each row of a provider."""
    out = []
    for row in PROVIDERS[key][3]:
        suffix, style = row[0], row[1]
        label, tmdb_type, params = row[2] if len(row) > 2 else ROWS[suffix]
        out.append((suffix, style, label, tmdb_type, params))
    return out


def build_includes() -> str:
    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!-- DEFLIX - generated by tools/build_providers.py, do not edit by hand -->",
        "<includes>",
        "",
        "\t<!-- Country whose streaming catalogues are shown (Skin Settings), US if unset -->",
        '\t<variable name="Provider_Region">',
        '\t\t<value condition="!String.IsEmpty(Skin.String(DeflixRegion))">$INFO[Skin.String(DeflixRegion)]</value>',
        "\t\t<value>US</value>",
        "\t</variable>",
        "",
    ]
    for key, (_group, provider_id, spotlight_type, _rows) in PROVIDERS.items():
        out.append(f"\t<!-- {key} -->")
        out.append(variable(f"Provider_{key}_Spotlight", discover_path(provider_id, spotlight_type, SPOTLIGHT)))
        for suffix, _style, _label, tmdb_type, params in provider_rows(key):
            out.append(variable(f"Provider_{key}_{suffix}", discover_path(provider_id, tmdb_type, params)))
    out += ["</includes>", ""]
    return "\n".join(out)


def build_hub(key: str) -> str:
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<!-- DEFLIX - generated by tools/build_providers.py -->", "<shortcuts>"]
    for suffix, _style, label, _tmdb_type, _params in provider_rows(key):
        out += [
            "    <shortcut>",
            f"        <label>$LOCALIZE[{label}]</label>",
            "        <label2 />",
            "        <icon />",
            "        <thumb />",
            f"        <action>$VAR[Provider_{key}_{suffix}]</action>",
            "    </shortcut>",
        ]
    out += ["</shortcuts>", ""]
    return "\n".join(out)


STYLES_START = "\t<!-- provider row styles: generated by tools/build_providers.py -->"
STYLES_END = "\t<!-- end provider row styles -->"


def write_row_styles() -> None:
    """Record each row's style as a Skin Shortcuts property default, keyed by its label id."""
    lines = [STYLES_START]
    for key, (group, _provider_id, _spotlight_type, _rows) in PROVIDERS.items():
        for _suffix, style, label, _tmdb_type, _params in provider_rows(key):
            if style:
                lines.append(f'\t<propertydefault labelID="{label}" group="{group}" property="widgetstyle">{style}</propertydefault>')
    lines.append(STYLES_END)
    path = ROOT / "shortcuts" / "overrides.xml"
    text = path.read_text(encoding="utf-8")
    start, end = text.index(STYLES_START), text.index(STYLES_END) + len(STYLES_END)
    path.write_text(text[:start] + "\n".join(lines) + text[end:], encoding="utf-8")


def main() -> None:
    (ROOT / "1080i" / "IncludesProviders.xml").write_text(build_includes(), encoding="utf-8")
    for key, (group, *_rest) in PROVIDERS.items():
        (ROOT / "shortcuts" / f"{group}.DATA.xml").write_text(build_hub(key), encoding="utf-8")
    write_row_styles()
    print("Wrote", ", ".join(f"{key} ({len(provider_rows(key))} rows)" for key in PROVIDERS))


if __name__ == "__main__":
    main()
