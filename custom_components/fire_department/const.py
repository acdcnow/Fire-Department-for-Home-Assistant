"""Constants for the Fire Department Austria integration."""

from __future__ import annotations

from .provider import CATEGORIES, CATEGORY_LABELS  # noqa: F401 - re-exported

DOMAIN = "fire_department"
NAME = "Fire Department Austria"
DEFAULT_NAME = "Fire Department"

# --------------------------------------------------------------------------- #
# config entry / options keys
# --------------------------------------------------------------------------- #
CONF_REGION = "region"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_SOURCES = "sources"
CONF_COLOR_SCHEME = "color_scheme"
CONF_FILTER_CATEGORIES = "filter_categories"
CONF_MAX_ITEMS = "max_items"
CONF_NAME = "name"

#: value of a "not used" selection in the options flow
NONE = "none"

# custom source ("page") keys
CONF_PAGES = "pages"
CONF_PAGE_NAME = "name"
CONF_PAGE_URL = "url"
CONF_PAGE_PARSER = "parser"
CONF_PAGE_KIND = "kind"
CONF_PAGE_WINDOW = "window"
CONF_PAGE_FILTER = "filter"
CONF_PAGE_EXPAND = "expand"
CONF_PAGE_SELECTION = "pages_to_remove"

DEFAULT_UPDATE_INTERVAL = 30
MIN_UPDATE_INTERVAL = 5
MAX_UPDATE_INTERVAL = 720

#: Home Assistant drops state attributes above 16 KiB, so the exposed row list
#: is capped.  The sensor state always reports the full count.
DEFAULT_MAX_ITEMS = 25
MIN_MAX_ITEMS = 0
MAX_MAX_ITEMS = 200

DEFAULT_COLOR_SCHEME = "severity"
COLOR_SCHEMES = ("severity", "category", "source", "source_color", "none")

CONFIG_ENTRY_VERSION = 2
CONFIG_ENTRY_MINOR_VERSION = 1

# --------------------------------------------------------------------------- #
# sensor kinds
# --------------------------------------------------------------------------- #
KIND_ACTIVE = "active_operations"
KIND_UNITS = "deployed_fire_brigade"
KIND_HISTORY = "completed_missions"
KINDS = (KIND_ACTIVE, KIND_UNITS, KIND_HISTORY)

KIND_ICONS = {
    KIND_ACTIVE: "mdi:fire-alert",
    KIND_UNITS: "mdi:fire-truck",
    KIND_HISTORY: "mdi:history",
}

KIND_WINDOW = {KIND_ACTIVE: "live", KIND_UNITS: "live", KIND_HISTORY: "24h"}

# --------------------------------------------------------------------------- #
# parsers
# --------------------------------------------------------------------------- #
PARSER_WASTL_INCIDENTS = "wastl_incidents"
PARSER_WASTL_UNITS = "wastl_units"
PARSER_OOE = "ooe"
PARSER_STMK_CSV = "stmk_csv"

PARSERS = (PARSER_WASTL_INCIDENTS, PARSER_WASTL_UNITS, PARSER_OOE, PARSER_STMK_CSV)

FILTERS = (None, "ongoing", "closed")
WINDOWS = ("live", "24h", "month", "custom")

# --------------------------------------------------------------------------- #
# regions
# --------------------------------------------------------------------------- #
REGION_NOE = "lower_austria"
REGION_OOE = "upper_austria"
REGION_STMK = "styria"
REGION_VIENNA = "vienna"
REGION_SBG = "salzburg"
REGION_BGLD = "burgenland"
REGION_KTN = "carinthia"
REGION_TIR = "tyrol"
REGION_VBG = "vorarlberg"

# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #
WASTL_BASE = "https://www.feuerwehr-krems.at/codepages/wastl/wastlmain/"
OOE_BASE = "https://einsaetze.ooelfv.at/einsatz/"
STMK_CSV_URL = "https://einsatzuebersicht.lfv.steiermark.at/lfvasp/einsatzkarte/Public.aspx?view=24"

SOURCES: dict[str, dict] = {
    # ---- Lower Austria (WASTL, hosted by the Krems fire brigade) ---------- #
    "noe_active": {
        "id": "noe_active",
        "region": REGION_NOE,
        "url": f"{WASTL_BASE}Land_EinsatzAktuell.asp",
        "parser": PARSER_WASTL_INCIDENTS,
        "kind": KIND_ACTIVE,
        "window": "live",
    },
    "noe_units": {
        "id": "noe_units",
        "region": REGION_NOE,
        "url": f"{WASTL_BASE}Land_FFimEinsatz.asp",
        "parser": PARSER_WASTL_UNITS,
        "kind": KIND_UNITS,
        "window": "live",
    },
    "noe_history": {
        "id": "noe_history",
        "region": REGION_NOE,
        "url": "https://www.feuerwehr-krems.at/CodePages/Wastl/WastlMain/Land_EinsatzHistorie.asp",
        "parser": PARSER_WASTL_INCIDENTS,
        "kind": KIND_HISTORY,
        "window": "24h",
    },
    # ---- Upper Austria (ÖO. Landes-Feuerwehrverband mission list) --------- #
    "ooe_active": {
        "id": "ooe_active",
        "region": REGION_OOE,
        "url": f"{OOE_BASE}aktuell",
        "parser": PARSER_OOE,
        "kind": KIND_ACTIVE,
        "window": "live",
        "filter": "ongoing",
    },
    "ooe_units": {
        "id": "ooe_units",
        "region": REGION_OOE,
        "url": f"{OOE_BASE}aktuell",
        "parser": PARSER_OOE,
        "kind": KIND_UNITS,
        "window": "live",
        "filter": "ongoing",
        "expand": "units",
    },
    "ooe_history": {
        "id": "ooe_history",
        "region": REGION_OOE,
        "url": f"{OOE_BASE}tag",
        "parser": PARSER_OOE,
        "kind": KIND_HISTORY,
        "window": "24h",
        "filter": "closed",
    },
    # ---- Styria (semicolon separated mission list of the LFV) ------------- #
    "stmk_active": {
        "id": "stmk_active",
        "region": REGION_STMK,
        "url": STMK_CSV_URL,
        "parser": PARSER_STMK_CSV,
        "kind": KIND_ACTIVE,
        "window": "24h",
        "filter": "ongoing",
    },
    "stmk_units": {
        "id": "stmk_units",
        "region": REGION_STMK,
        "url": STMK_CSV_URL,
        "parser": PARSER_STMK_CSV,
        "kind": KIND_UNITS,
        "window": "24h",
        "filter": "ongoing",
        "expand": "units",
    },
    "stmk_history": {
        "id": "stmk_history",
        "region": REGION_STMK,
        "url": STMK_CSV_URL,
        "parser": PARSER_STMK_CSV,
        "kind": KIND_HISTORY,
        "window": "24h",
        "filter": "closed",
    },
}

#: region -> {kind: source id}
REGIONS: dict[str, dict[str, str]] = {
    REGION_NOE: {KIND_ACTIVE: "noe_active", KIND_UNITS: "noe_units", KIND_HISTORY: "noe_history"},
    REGION_OOE: {KIND_ACTIVE: "ooe_active", KIND_UNITS: "ooe_units", KIND_HISTORY: "ooe_history"},
    REGION_STMK: {KIND_ACTIVE: "stmk_active", KIND_UNITS: "stmk_units", KIND_HISTORY: "stmk_history"},
    # No verified machine readable mission list yet - see the README for the
    # candidate pages of these federal states.
    REGION_VIENNA: {},
    REGION_SBG: {},
    REGION_BGLD: {},
    REGION_KTN: {},
    REGION_TIR: {},
    REGION_VBG: {},
}

#: regions that can be selected in the config flow
SUPPORTED_REGIONS = tuple(region for region, sources in REGIONS.items() if sources)

#: human readable region names (used for the device model)
REGION_LABELS = {
    REGION_NOE: "Lower Austria – WASTL",
    REGION_OOE: "Upper Austria – LFV OÖ",
    REGION_STMK: "Styria – LFV Steiermark",
    REGION_VIENNA: "Vienna",
    REGION_SBG: "Salzburg",
    REGION_BGLD: "Burgenland",
    REGION_KTN: "Carinthia",
    REGION_TIR: "Tyrol",
    REGION_VBG: "Vorarlberg",
}

#: sources of a region in the order they should be created
def region_sources(region: str) -> dict[str, dict]:
    """Return the source definitions of a region."""
    return {
        SOURCES[source_id]["kind"]: dict(SOURCES[source_id])
        for source_id in REGIONS.get(region, {}).values()
    }


def build_sources(options: dict) -> list[dict]:
    """Materialise the configured sources of a config entry.

    ``options[CONF_SOURCES]`` maps a kind to a source id, ``options[CONF_PAGES]``
    holds user defined sources.  Returns a list of source dictionaries ready for
    :func:`provider.parse_source`.
    """
    configured = options.get(CONF_SOURCES) or {}
    sources: list[dict] = []
    for kind in KINDS:
        source_id = configured.get(kind)
        if not source_id:
            continue
        template = SOURCES.get(source_id)
        if template:
            sources.append(dict(template))
    seen_urls = {(source["url"], source["parser"], source.get("filter")) for source in sources}
    for index, page in enumerate(options.get(CONF_PAGES) or []):
        url = (page.get(CONF_PAGE_URL) or "").strip()
        parser = page.get(CONF_PAGE_PARSER) or PARSER_WASTL_INCIDENTS
        if not url or parser not in PARSERS:
            continue
        kind = page.get(CONF_PAGE_KIND) or KIND_HISTORY
        key = (url, parser, page.get(CONF_PAGE_FILTER))
        if key in seen_urls:
            continue
        seen_urls.add(key)
        sources.append(
            {
                "id": f"custom_{index}",
                "region": "custom",
                "url": url,
                "parser": parser,
                "kind": kind,
                "window": page.get(CONF_PAGE_WINDOW) or KIND_WINDOW.get(kind, "custom"),
                "filter": page.get(CONF_PAGE_FILTER) or None,
                "expand": page.get(CONF_PAGE_EXPAND) or None,
                "label": page.get(CONF_PAGE_NAME) or url,
            }
        )
    return sources


SIGNAL_NEW_INCIDENT = f"{DOMAIN}_new_incident"
SIGNAL_INCIDENT_CLOSED = f"{DOMAIN}_incident_closed"
