"""Tests for the Fire Department Austria integration.

Run with a plain Python interpreter, no Home Assistant needed::

    python tests/test_integration.py

A tiny Home Assistant stand-in (``tests/ha_stub.py``) provides the classes the
integration imports, and the parser tests run against the documents in
``tests/fixtures``.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import sys
from datetime import datetime
from urllib.parse import urlencode

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if os.environ.get("FD_LIBS"):
    sys.path.insert(0, os.environ["FD_LIBS"])

import ha_stub  # noqa: E402

ha_stub.install()

from custom_components.fire_department import binary_sensor as binary_sensor_module  # noqa: E402
from custom_components.fire_department import config_flow as config_flow_module  # noqa: E402
from custom_components.fire_department import const  # noqa: E402
from custom_components.fire_department import coordinator as coordinator_module  # noqa: E402
from custom_components.fire_department import diagnostics as diagnostics_module  # noqa: E402
from custom_components.fire_department import geocoding as geocoding_module  # noqa: E402
from custom_components.fire_department import geo_location as geo_location_module  # noqa: E402
from custom_components.fire_department import provider as P  # noqa: E402
from custom_components.fire_department import sensor as sensor_module  # noqa: E402

integration = sys.modules["custom_components.fire_department"]

FIXTURES = HERE / "fixtures"
FAILURES: list[str] = []


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def check(condition, message: str) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        FAILURES.append(message)
        print(f"  FAIL {message}")


def equal(actual, expected, message: str) -> None:
    check(actual == expected, f"{message} (got {actual!r}, expected {expected!r})")


class Collector(list):
    """List that doubles as the ``async_add_entities`` callback."""

    def __call__(self, entities):
        self.extend(entities if isinstance(entities, (list, tuple)) else [entities])


def make_options_flow(hass, entry):
    """Options flows are created without arguments, Home Assistant sets hass/handler."""
    flow = config_flow_module.FireDepartmentOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    return flow


def wastl_document(name: str) -> bytes:
    """WASTL pages are windows-1252 - feed them as such."""
    return (FIXTURES / name).read_text(encoding="utf-8").encode("cp1252")


def ooe_document() -> bytes:
    return (FIXTURES / "ooe_liste.html").read_bytes()


def stmk_document() -> bytes:
    return (FIXTURES / "stmk_liste.csv").read_bytes()


def documents() -> dict[str, bytes]:
    """Fixture document for every URL of the source catalogue."""
    noe_active = const.SOURCES["noe_active"]["url"]
    noe_units = const.SOURCES["noe_units"]["url"]
    noe_history = const.SOURCES["noe_history"]["url"]
    ooe_active = const.SOURCES["ooe_active"]["url"]
    ooe_history = const.SOURCES["ooe_history"]["url"]
    stmk = const.SOURCES["stmk_active"]["url"]
    return {
        noe_active: wastl_document("wastl_aktuell.html"),
        noe_units: wastl_document("wastl_ffim.html"),
        noe_history: wastl_document("wastl_historie.html"),
        ooe_active: ooe_document(),
        ooe_history: ooe_document(),
        stmk: stmk_document(),
    }


def options_for(region: str) -> dict:
    sources = {kind: source["id"] for kind, source in const.region_sources(region).items()}
    return {
        const.CONF_REGION: region,
        const.CONF_SOURCES: sources,
        const.CONF_UPDATE_INTERVAL: 30,
        const.CONF_COLOR_SCHEME: "severity",
        const.CONF_FILTER_CATEGORIES: [],
        const.CONF_MAX_ITEMS: const.DEFAULT_MAX_ITEMS,
        const.CONF_PAGES: [],
    }


async def setup_region(region: str, docs: dict[str, bytes] | None = None):
    hass = ha_stub.FakeHass(ha_stub.Session(docs if docs is not None else documents()))
    entry = ha_stub.add_entry(hass, title="Test", options=options_for(region))
    ok = await integration.async_setup_entry(hass, entry)
    return hass, entry, ok


# --------------------------------------------------------------------------- #
# parser tests
# --------------------------------------------------------------------------- #
def test_parser_lower_austria_active() -> None:
    print("\n[parser] Lower Austria - active missions")
    source = dict(const.SOURCES["noe_active"])
    text = P.decode_bytes(wastl_document("wastl_aktuell.html"), None)
    rows = P.parse_source(text, source, datetime.now(P.TZ))
    equal(len(rows), 3, "row count")
    first = rows[0]
    equal(first["municipality"], "Musterdorf", "municipality")
    equal(first["station"], "Alarmzentrale", "station is the control centre")
    equal(first["type"], "B1 Brandmeldeanlage - Brand", "alert text")
    equal(first["keyword"], "B1", "keyword")
    equal(first["level"], 1, "level")
    equal(first["category"], "fire", "category")
    equal(first["severity"], "medium", "severity")
    equal(first["age"], "< 1 std.", "relative age")
    equal(first["started"], None, "no absolute timestamp on this page")
    equal(first["running"], True, "live rows are running")
    equal(first["date"], "19.09.2026", "date")
    equal(rows[2]["category"], "exercise", "exercise detected")
    equal(rows[2]["severity"], "info", "exercises are informational")
    check(all(len(row["id"]) == 16 for row in rows), "stable ids")


def test_parser_lower_austria_units() -> None:
    print("\n[parser] Lower Austria - deployed brigades")
    source = dict(const.SOURCES["noe_units"])
    text = P.decode_bytes(wastl_document("wastl_ffim.html"), None)
    rows = P.parse_source(text, source, datetime.now(P.TZ))
    equal(len(rows), 3, "row count")
    equal(rows[0]["brigade_code"], "140302", "brigade number is kept")
    equal(rows[0]["brigade"], "Musterdorf", "brigade name")
    equal(rows[0]["municipality"], "Musterdorf", "municipality")
    equal(rows[1]["category"], "technical", "category of T1")
    equal(rows[0]["kind"], const.KIND_UNITS, "kind")


def test_parser_lower_austria_history() -> None:
    print("\n[parser] Lower Austria - mission history")
    source = dict(const.SOURCES["noe_history"])
    text = P.decode_bytes(wastl_document("wastl_historie.html"), None)
    rows = P.parse_source(text, source, datetime.now(P.TZ))
    equal(len(rows), 3, "row count")
    check(rows[0]["started"].startswith("2026-09-19T15:22:00"), "absolute timestamp parsed")
    equal(rows[1]["category"], "hazardous", "S1 is hazardous goods")
    equal(rows[2]["keyword"], "SOF1", "multi letter keyword")
    equal(rows[2]["category"], "special", "SOF is special")
    equal(rows[2]["level"], 1, "SOF1 carries a level")
    equal(rows[2]["severity"], "medium", "level 1 is medium")


def test_parser_upper_austria() -> None:
    print("\n[parser] Upper Austria")
    text = P.decode_bytes(ooe_document(), "utf-8")
    raw = {**dict(const.SOURCES["ooe_active"]), "filter": None}
    rows = P.parse_source(text, raw, datetime.now(P.TZ))
    equal(len(rows), 3, "row count without the running filter")
    first = rows[0]
    equal(first["municipality"], "Handenberg", "municipality")
    equal(first["district"], "Braunau", "district from the link title")
    equal(first["district_code"], "BR", "district code")
    equal(first["type"], "Brandverdacht", "alert text without the unit list")
    equal(first["category"], "fire", "red chip = fire")
    equal(first["severity"], "high", "red chip = high")
    equal(first["source_color"], "red", "raw source colour")
    equal(first["unit_count"], 1, "one brigade")
    equal(first["units"][0]["name"], "Feuerwehr Handenberg", "unit name")
    equal(first["running"], True, "no end time = running")
    equal(first["color"], "#dc2626", "severity colour")

    second = rows[1]
    equal(second["unit_count"], 2, "two brigades")
    equal(second["running"], False, "end times present = finished")
    equal(second["ended"][11:16], "15:34", "end time gets the day of the start")
    equal(second["duration_minutes"], 24, "duration")
    equal(second["severity"], "medium", "yellow chip")
    equal(rows[2]["category"], "technical", "blue chip = technical")
    equal(rows[2]["district_code"], "UU", "district code of row 2")

    filtered = P.parse_source(text, dict(const.SOURCES["ooe_active"]), datetime.now(P.TZ))
    equal(len(filtered), 1, "the source filter keeps only the running mission")
    closed = P.parse_source(text, dict(const.SOURCES["ooe_history"]), datetime.now(P.TZ))
    equal(len(closed), 2, "history filter keeps the finished missions")


def test_parser_styria() -> None:
    print("\n[parser] Styria (CSV)")
    source = dict(const.SOURCES["stmk_active"])
    text = P.decode_bytes(b"\xef\xbb\xbf" + stmk_document(), "text/csv")
    rows = P.parse_source(text, source, datetime.now(P.TZ))
    equal(len(rows), 2, "only the running missions survive the filter")
    equal(rows[0]["municipality"], "Arnfels", "municipality")
    equal(rows[0]["district_code"], "LB", "district code")
    equal(rows[0]["keyword"], "T01", "keyword from sub_tycod")
    equal(rows[0]["category"], "technical", "category")
    equal(rows[0]["unit_count"], 1, "assigned units")
    equal(rows[0]["running"], True, "assigned units > 0 = running")
    equal(rows[0]["date_only"], True, "no time in the CSV")
    equal(rows[0]["color"], "#2563eb", "low severity colour")

    closed = P.parse_source(text, dict(const.SOURCES["stmk_history"]), datetime.now(P.TZ))
    equal(len(closed), 2, "finished missions of the 24 h window")
    equal(closed[0]["keyword"], "T05", "keyword")
    equal(closed[0]["running"], False, "0 units = finished")

    units = P.parse_source(text, dict(const.SOURCES["stmk_units"]), datetime.now(P.TZ))
    equal(len(units), 2, "expanded unit rows")


def test_parser_helpers() -> None:
    print("\n[parser] helpers")
    sample = "St. P\u00f6lten \u2013 T\u00fcr\u00f6ffnung"
    equal(P.decode_bytes(sample.encode("cp1252"), None), sample, "cp1252 sniffing")
    equal(P.decode_bytes(sample.encode("utf-8"), "UTF-8"), sample, "utf-8 hint")
    equal(P.decode_bytes(b"\xef\xbb\xbfa;b", "text/csv"), "a;b", "BOM removed")
    equal(P.split_keyword("B1 Gefahrenmeldeanlage - Brand"), ("B", "B1", 1), "split B1")
    equal(P.split_keyword("T03V-VU-mit-Verl"), ("T", "T03V", None), "no level for two digits")
    equal(P.split_keyword("Brandverdacht"), (None, None, None), "plain text")
    equal(P.category_for("SOF", "SOF1"), "special", "SOF category")
    equal(P.severity_for("fire", 2), "high", "B2 is high")
    equal(P.color_for("category", "technical", "low", "ooe"), "#2563eb", "category colour")
    equal(P.color_for("none", "fire", "high", "noe"), None, "colour scheme none")
    equal(P.color_legend("severity")["high"], "#dc2626", "legend")
    equal(P.humanize_duration(95), "1 h 35 min", "humanized duration")
    check(P.sort_rows([{"started": "b"}, {"started": "a"}])[0]["started"] == "b", "newest first")

    rows = P.parse_source(
        P.decode_bytes(wastl_document("wastl_historie.html"), None),
        dict(const.SOURCES["noe_history"]),
        datetime.now(P.TZ),
    )
    equal(len(P.parse_source("", dict(const.SOURCES["noe_history"]), datetime.now(P.TZ))), 0, "empty page")
    summary = P.summarize(rows)
    equal(sum(summary["by_category"].values()), 3, "category counters")
    equal(summary["by_keyword"]["T1"], 1, "keyword counters")


def test_category_filter() -> None:
    print("\n[parser] category filter")
    source = dict(const.SOURCES["noe_history"])
    text = P.decode_bytes(wastl_document("wastl_historie.html"), None)
    rows = P.parse_source(text, source, datetime.now(P.TZ), "severity", ["fire"])
    equal(len(rows), 0, "only fire rows survive")
    rows = P.parse_source(text, source, datetime.now(P.TZ), "severity", ["hazardous"])
    equal(len(rows), 1, "hazardous filter")


# --------------------------------------------------------------------------- #
# integration tests
# --------------------------------------------------------------------------- #
def test_setup_entry() -> None:
    print("\n[integration] setup entry (Lower Austria)")
    hass, entry, ok = ha_stub.run(setup_region(const.REGION_NOE))
    check(ok, "async_setup_entry returned True")
    coordinator = entry.runtime_data
    equal(sorted(coordinator.data), ["noe_active", "noe_history", "noe_units"], "data per source")
    equal(len(coordinator.data["noe_active"]), 3, "active rows")
    equal(coordinator.update_interval, __import__("datetime").timedelta(minutes=30), "interval")
    equal(len(coordinator.sources), 3, "three sources")
    equal(coordinator.fetched_at is not None, True, "fetched_at set")
    equal(coordinator.last_error, None, "no error")
    equal(
        hass.config_entries.forwarded[0][1],
        ("sensor", "binary_sensor", "geo_location"),
        "platforms forwarded",
    )
    equal(len(entry._listeners), 1, "reload listener registered")

    equal(hass.config_entries.unloaded, [], "nothing unloaded yet")
    check(ha_stub.run(integration.async_unload_entry(hass, entry)), "unload works")
    equal(hass.config_entries.unloaded, [entry.entry_id], "unload recorded")
    ha_stub.run(integration.async_reload_entry(hass, entry))
    equal(hass.config_entries.reloads, [entry.entry_id], "reload triggered")
    return hass, entry


def test_entities() -> None:
    print("\n[integration] entities")
    hass, entry, _ = ha_stub.run(setup_region(const.REGION_NOE))
    sensors = Collector()
    ha_stub.run(sensor_module.async_setup_entry(hass, entry, sensors))
    equal(len(sensors), 3, "three sensors")
    by_key = {entity.translation_key: entity for entity in sensors}
    equal(
        sorted(by_key),
        [const.KIND_ACTIVE, const.KIND_HISTORY, const.KIND_UNITS],
        "translation keys",
    )
    equal(by_key[const.KIND_ACTIVE].native_value, 3, "active count")
    equal(by_key[const.KIND_UNITS].native_value, 3, "unit count")
    equal(by_key[const.KIND_HISTORY].native_value, 3, "history count")
    check(all(entity.available for entity in sensors), "all available")

    attributes = by_key[const.KIND_ACTIVE].extra_state_attributes
    equal(attributes["count"], 3, "count attribute")
    equal(len(attributes["incidents"]), 3, "rows exposed")
    equal(attributes["truncated"], False, "not truncated")
    equal(attributes["by_category"], {"fire": 1, "technical": 1, "exercise": 1}, "category counters")
    equal(attributes["latest_incident"]["municipality"], "Musterdorf", "newest first")
    equal(attributes["source_url"], const.SOURCES["noe_active"]["url"], "source url")
    equal(attributes["color_legend"]["high"], "#dc2626", "legend attribute")
    equal(attributes["longest_running"]["running"], True, "longest running helper")

    history_attributes = by_key[const.KIND_HISTORY].extra_state_attributes
    check("average_duration_minutes" not in history_attributes, "no durations for WASTL history")
    equal(by_key[const.KIND_ACTIVE].device_info["identifiers"], {(const.DOMAIN, entry.entry_id)}, "device info")

    binaries: list = Collector()
    ha_stub.run(binary_sensor_module.async_setup_entry(hass, entry, binaries))
    equal(len(binaries), 1, "one binary sensor")
    equal(binaries[0].is_on, True, "missions running")
    equal(binaries[0]._attr_device_class, "safety", "device class")
    equal(binaries[0].translation_key, const.KIND_ACTIVE, "translation key")
    equal(binaries[0].extra_state_attributes["count"], 3, "count attribute")


def test_max_items_and_filter() -> None:
    print("\n[integration] row limit and category filter")
    options = options_for(const.REGION_NOE)
    options[const.CONF_MAX_ITEMS] = 1
    options[const.CONF_FILTER_CATEGORIES] = ["fire"]
    hass = ha_stub.FakeHass(ha_stub.Session(documents()))
    entry = ha_stub.add_entry(hass, title="Limited", options=options)
    ha_stub.run(integration.async_setup_entry(hass, entry))
    sensors = Collector()
    ha_stub.run(sensor_module.async_setup_entry(hass, entry, sensors))
    active = next(entity for entity in sensors if entity.translation_key == const.KIND_ACTIVE)
    equal(active.native_value, 1, "filtered count")
    attributes = active.extra_state_attributes
    equal(len(attributes["incidents"]), 1, "one row shown")
    equal(attributes["truncated"], False, "nothing left to truncate")
    equal(attributes["filter_categories"], ["fire"], "filter reported")

    options_zero = options_for(const.REGION_NOE)
    options_zero[const.CONF_MAX_ITEMS] = 0
    hass = ha_stub.FakeHass(ha_stub.Session(documents()))
    entry = ha_stub.add_entry(hass, title="No rows", options=options_zero)
    ha_stub.run(integration.async_setup_entry(hass, entry))
    sensors = Collector()
    ha_stub.run(sensor_module.async_setup_entry(hass, entry, sensors))
    attributes = next(e for e in sensors if e.translation_key == const.KIND_ACTIVE).extra_state_attributes
    equal(attributes["incidents"], [], "0 = no rows in the attributes")
    equal(attributes["truncated"], True, "truncation reported")


def test_events() -> None:
    print("\n[integration] automation events")
    source = const.SOURCES["noe_active"]["url"]
    docs = documents()
    hass = ha_stub.FakeHass(ha_stub.Session(docs))
    entry = ha_stub.add_entry(hass, title="Events", options=options_for(const.REGION_NOE))
    ha_stub.run(integration.async_setup_entry(hass, entry))
    coordinator = entry.runtime_data
    equal(len(hass.bus.events), 0, "no events on the first refresh")

    docs[source] = wastl_document("wastl_historie.html")  # completely different rows
    ha_stub.run(coordinator.async_refresh())
    fired = [name for name, _data in hass.bus.events]
    equal(fired.count(const.SIGNAL_NEW_INCIDENT), 3, "three new missions")
    equal(fired.count(const.SIGNAL_INCIDENT_CLOSED), 3, "three finished missions")
    payload = hass.bus.events[0][1]
    equal(payload["source"], "noe_active", "payload source")
    check("incident" in payload and "entry_id" in payload, "payload keys")


def test_partial_failure() -> None:
    print("\n[integration] one source down")
    docs = documents()
    del docs[const.SOURCES["noe_history"]["url"]]
    hass, entry, ok = ha_stub.run(setup_region(const.REGION_NOE, docs))
    check(ok, "setup still succeeds")
    coordinator = entry.runtime_data
    equal(sorted(coordinator.failed_sources), ["noe_history"], "failed source reported")
    check(coordinator.last_error, "last_error set")
    sensors: list = Collector()
    ha_stub.run(sensor_module.async_setup_entry(hass, entry, sensors))
    states = {entity.translation_key: entity.available for entity in sensors}
    equal(states[const.KIND_HISTORY], False, "history sensor unavailable")
    equal(states[const.KIND_ACTIVE], True, "active sensor available")
    equal(
        sorted(coordinator.data),
        ["noe_active", "noe_units"],
        "only readable sources in the data",
    )


def test_total_failure() -> None:
    print("\n[integration] all sources down")
    hass = ha_stub.FakeHass(ha_stub.Session({}))
    entry = ha_stub.add_entry(hass, title="Down", options=options_for(const.REGION_NOE))
    try:
        ha_stub.run(integration.async_setup_entry(hass, entry))
        check(False, "setup must not succeed")
    except ha_stub.UpdateFailed as error:
        check("No source could be read" in str(error), "UpdateFailed raised")


def test_shared_url_is_fetched_once() -> None:
    print("\n[integration] shared URL")
    hass, entry, _ = ha_stub.run(setup_region(const.REGION_STMK))
    session = hass.session
    equal(len(session.requests), 1, "Styrian CSV downloaded once for three sensors")
    equal(len(entry.runtime_data.data), 3, "three sources parsed")


def test_upper_austria_setup() -> None:
    print("\n[integration] Upper Austria")
    hass, entry, _ = ha_stub.run(setup_region(const.REGION_OOE))
    coordinator = entry.runtime_data
    sensors = Collector()
    ha_stub.run(sensor_module.async_setup_entry(hass, entry, sensors))
    by_key = {entity.translation_key: entity for entity in sensors}
    equal(by_key[const.KIND_ACTIVE].native_value, 1, "running missions")
    equal(by_key[const.KIND_UNITS].native_value, 1, "brigades of the running mission")
    equal(by_key[const.KIND_HISTORY].native_value, 2, "finished missions")
    durations = by_key[const.KIND_HISTORY].extra_state_attributes["average_duration_minutes"]
    equal(durations, 31, "average duration (24 and 38 minutes)")
    equal(len(coordinator.failed_sources), 0, "no failed source")


def test_custom_source() -> None:
    print("\n[integration] custom source")
    options = options_for(const.REGION_NOE)
    options[const.CONF_PAGES] = [
        {
            const.CONF_PAGE_NAME: "My own table",
            const.CONF_PAGE_URL: "https://example.invalid/missions.asp",
            const.CONF_PAGE_PARSER: const.PARSER_WASTL_INCIDENTS,
            const.CONF_PAGE_KIND: const.KIND_HISTORY,
            const.CONF_PAGE_WINDOW: "custom",
        }
    ]
    docs = documents()
    docs["https://example.invalid/missions.asp"] = wastl_document("wastl_historie.html")
    hass = ha_stub.FakeHass(ha_stub.Session(docs))
    entry = ha_stub.add_entry(hass, title="Custom", options=options)
    ha_stub.run(integration.async_setup_entry(hass, entry))
    equal(len(entry.runtime_data.sources), 4, "custom source added")
    sensors = Collector()
    ha_stub.run(sensor_module.async_setup_entry(hass, entry, sensors))
    custom = [entity for entity in sensors if entity.name == "My own table"]
    equal(len(custom), 1, "custom sensor created")
    equal(custom[0].native_value, 3, "custom rows parsed")
    check(custom[0].translation_key is None, "custom sensor uses a plain name")


def test_diagnostics() -> None:
    print("\n[integration] diagnostics")
    hass, entry, _ = ha_stub.run(setup_region(const.REGION_OOE))
    diag = ha_stub.run(diagnostics_module.async_get_config_entry_diagnostics(hass, entry))
    equal(diag["entry"]["version"], 2, "version reported")
    equal(diag["last_update_success"], True, "success flag")
    equal(diag["data"]["ooe_active"]["count"], 1, "count per source")
    check(json.dumps(diag), "diagnostics are serialisable")


# --------------------------------------------------------------------------- #
# config flow tests
# --------------------------------------------------------------------------- #
def test_config_flow() -> None:
    print("\n[config flow] user step")
    hass = ha_stub.FakeHass()
    flow = config_flow_module.FireDepartmentConfigFlow()
    flow.hass = hass
    form = ha_stub.run(flow.async_step_user())
    equal(form["type"], "form", "form shown")
    schema = form["data_schema"].schema
    check(const.CONF_REGION in {key.schema if hasattr(key, "schema") else key for key in schema}, "region field")

    result = ha_stub.run(
        flow.async_step_user(
            {
                "name": "My fire brigade",
                const.CONF_REGION: const.REGION_STMK,
                const.CONF_UPDATE_INTERVAL: 15,
                const.CONF_COLOR_SCHEME: "category",
                const.CONF_FILTER_CATEGORIES: ["fire", "technical"],
            }
        )
    )
    equal(result["type"], "create_entry", "entry created")
    equal(result["title"], "My fire brigade", "title")
    options = result["options"]
    equal(
        options[const.CONF_SOURCES],
        {const.KIND_ACTIVE: "stmk_active", const.KIND_UNITS: "stmk_units", const.KIND_HISTORY: "stmk_history"},
        "sources of the region",
    )
    equal(options[const.CONF_UPDATE_INTERVAL], 15, "interval stored")
    equal(options[const.CONF_COLOR_SCHEME], "category", "colour scheme stored")
    equal(flow.unique_id, const.REGION_STMK, "unique id")

    hass.config_entries.unique_ids.add(const.REGION_STMK)
    try:
        ha_stub.run(flow.async_step_user({"name": "again", const.CONF_REGION: const.REGION_STMK}))
        check(False, "duplicate region must abort")
    except ha_stub.AbortFlow as abort:
        equal(abort.reason, "already_configured", "abort reason")


def test_options_flow() -> None:
    print("\n[config flow] options")
    hass = ha_stub.FakeHass(ha_stub.Session(documents()))
    entry = ha_stub.add_entry(hass, title="Options", options=options_for(const.REGION_NOE))
    flow = make_options_flow(hass, entry)

    menu = ha_stub.run(flow.async_step_init())
    equal(menu["type"], "menu", "menu shown")
    equal(
        menu["menu_options"],
        ["general", "sources", "add_page", "remove_page"],
        "menu entries",
    )

    general = ha_stub.run(flow.async_step_general())
    equal(general["step_id"], "general", "general form")
    saved = ha_stub.run(
        flow.async_step_general(
            {
                const.CONF_UPDATE_INTERVAL: 45,
                const.CONF_COLOR_SCHEME: "source",
                const.CONF_FILTER_CATEGORIES: ["fire"],
                const.CONF_MAX_ITEMS: 10,
            }
        )
    )
    equal(saved["type"], "create_entry", "options saved")
    equal(saved["data"][const.CONF_UPDATE_INTERVAL], 45, "interval stored")
    equal(saved["data"][const.CONF_MAX_ITEMS], 10, "max items stored")
    equal(saved["data"][const.CONF_FILTER_CATEGORIES], ["fire"], "filter stored")

    flow = make_options_flow(hass, entry)
    ha_stub.run(flow.async_step_init())
    sources_form = ha_stub.run(flow.async_step_sources())
    equal(sources_form["step_id"], "sources", "sources form")
    changed = ha_stub.run(
        flow.async_step_sources(
            {
                const.KIND_ACTIVE: "ooe_active",
                const.KIND_UNITS: "none",
                const.KIND_HISTORY: "noe_history",
            }
        )
    )
    equal(
        changed["data"][const.CONF_SOURCES],
        {const.KIND_ACTIVE: "ooe_active", const.KIND_HISTORY: "noe_history"},
        "kind without source removed",
    )

    flow = make_options_flow(hass, entry)
    ha_stub.run(flow.async_step_init())
    bad = ha_stub.run(
        flow.async_step_add_page(
            {const.CONF_PAGE_URL: "ftp://nope", const.CONF_PAGE_PARSER: const.PARSER_OOE}
        )
    )
    equal(bad["errors"], {const.CONF_PAGE_URL: "invalid_url"}, "url validated")
    page = ha_stub.run(
        flow.async_step_add_page(
            {
                const.CONF_PAGE_NAME: "Extra",
                const.CONF_PAGE_URL: "https://example.invalid/x.asp",
                const.CONF_PAGE_PARSER: const.PARSER_WASTL_INCIDENTS,
                const.CONF_PAGE_KIND: const.KIND_ACTIVE,
                const.CONF_PAGE_WINDOW: "live",
                const.CONF_PAGE_FILTER: "ongoing",
            }
        )
    )
    equal(len(page["data"][const.CONF_PAGES]), 1, "page added")
    equal(page["data"][const.CONF_PAGES][0][const.CONF_PAGE_FILTER], "ongoing", "filter stored")

    flow = make_options_flow(hass, entry)
    ha_stub.run(flow.async_step_init())
    aborted = ha_stub.run(flow.async_step_remove_page())
    equal(aborted["reason"], "no_pages", "abort without custom sources")

    entry.options[const.CONF_PAGES] = [
        {const.CONF_PAGE_NAME: "A", const.CONF_PAGE_URL: "https://a.invalid"},
        {const.CONF_PAGE_NAME: "B", const.CONF_PAGE_URL: "https://b.invalid"},
    ]
    flow = make_options_flow(hass, entry)
    ha_stub.run(flow.async_step_init())
    removed = ha_stub.run(flow.async_step_remove_page({const.CONF_PAGE_SELECTION: ["0"]}))
    equal(len(removed["data"][const.CONF_PAGES]), 1, "one page removed")
    equal(removed["data"][const.CONF_PAGES][0]["name"], "B", "correct page kept")


def test_migration() -> None:
    print("\n[integration] migration from version 1")
    hass = ha_stub.FakeHass(ha_stub.Session(documents()))
    legacy_pages = [
        {"name": "active_operations", "url": const.SOURCES["noe_active"]["url"], "type": "incidents"},
        {"name": "deployed_fire_brigade", "url": const.SOURCES["noe_units"]["url"], "type": "departments"},
        {"name": "completed_missions", "url": const.SOURCES["noe_history"]["url"], "type": "incidents"},
        {"name": "Special page", "url": "https://example.invalid/special.asp", "type": "incidents"},
    ]
    entry = ha_stub.add_entry(
        hass,
        title="Legacy",
        options={const.CONF_UPDATE_INTERVAL: 60, const.CONF_PAGES: legacy_pages},
        version=1,
        minor_version=1,
    )
    check(ha_stub.run(integration.async_migrate_entry(hass, entry)), "migration returns True")
    equal(entry.version, 2, "version bumped")
    equal(
        entry.options[const.CONF_SOURCES],
        {const.KIND_ACTIVE: "noe_active", const.KIND_UNITS: "noe_units", const.KIND_HISTORY: "noe_history"},
        "legacy urls mapped to source ids",
    )
    equal(len(entry.options[const.CONF_PAGES]), 1, "unknown page kept as custom source")
    equal(entry.options[const.CONF_MAX_ITEMS], const.DEFAULT_MAX_ITEMS, "new option added")
    equal(entry.options[const.CONF_UPDATE_INTERVAL], 60, "old option kept")
    # the migrated entry has to set up fine
    ha_stub.run(integration.async_setup_entry(hass, entry))
    equal(len(entry.runtime_data.sources), 4, "migrated entry sets up")

    entry.version = 9
    check(not ha_stub.run(integration.async_migrate_entry(hass, entry)), "future version refused")


def test_translations() -> None:
    print("\n[translations]")
    base = HERE.parent / "custom_components" / "fire_department"
    languages = {
        name: json.loads((base / "translations" / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("en", "de")
    }
    strings = json.loads((base / "strings.json").read_text(encoding="utf-8"))
    check(strings == languages["en"], "strings.json matches the English translation")

    source_code = (base / "config_flow.py").read_text(encoding="utf-8")
    used_keys = set(re.findall(r'translation_key="([a-z_]+)"', source_code))
    check(used_keys, "selector translation keys found in the source")
    for name, translations in languages.items():
        selectors = translations["selector"]
        for key in used_keys:
            check(key in selectors, f"{name}: selector.{key} exists")

    expected_options = {
        "region": set(const.SUPPORTED_REGIONS),
        "color_scheme": set(const.COLOR_SCHEMES),
        "category": set(config_flow_module.CATEGORY_OPTIONS),
        "parser": set(const.PARSERS),
        "kind": set(const.KINDS),
        "window": set(const.WINDOWS),
        "row_filter": {"none", "ongoing", "closed"},
        "source": set(const.SOURCES) | {"none"},
    }
    for name, translations in languages.items():
        for key, values in expected_options.items():
            missing = values - set(translations["selector"][key]["options"])
            check(not missing, f"{name}: selector.{key} translates every option (missing {sorted(missing)})")

    for name, translations in languages.items():
        for kind in const.KINDS:
            check(
                kind in translations["entity"]["sensor"],
                f"{name}: entity.sensor.{kind} exists",
            )
        check(
            const.KIND_ACTIVE in translations["entity"]["binary_sensor"],
            f"{name}: entity.binary_sensor.{const.KIND_ACTIVE} exists",
        )
        for step in ("init", "general", "sources", "add_page", "remove_page"):
            check(step in translations["options"]["step"], f"{name}: options.step.{step} exists")
        check("no_pages" in translations["options"]["abort"], f"{name}: abort no_pages")
        check("already_configured" in translations["config"]["abort"], f"{name}: abort already_configured")
        for error in ("invalid_url", "invalid_parser"):
            check(error in translations["options"]["error"], f"{name}: options.error.{error}")
            check(error in translations["config"]["error"], f"{name}: config.error.{error}")
        for key in ("name", "region", "update_interval", "color_scheme", "filter_categories"):
            check(key in translations["config"]["step"]["user"]["data"], f"{name}: config field {key}")
        for key in (
            const.CONF_UPDATE_INTERVAL,
            const.CONF_COLOR_SCHEME,
            const.CONF_FILTER_CATEGORIES,
            const.CONF_MAX_ITEMS,
            const.CONF_MAP_MARKERS,
        ):
            check(key in translations["options"]["step"]["general"]["data"], f"{name}: general field {key}")


def test_manifest() -> None:
    print("\n[manifest / hacs]")
    base = HERE.parent
    manifest = json.loads((base / "custom_components" / "fire_department" / "manifest.json").read_text())
    hacs = json.loads((base / "hacs.json").read_text())
    equal(manifest["domain"], "fire_department", "domain")
    equal(manifest["requirements"], [], "no external requirements")
    check("acdcnow/fire-department-for-Home-Assistant" in manifest["documentation"], "documentation link")
    check("acdcnow/fire-department-for-Home-Assistant" in manifest["issue_tracker"], "issue tracker link")
    check(manifest["version"].startswith("3.0.0"), "version")
    equal(hacs["homeassistant"], "2026.9.0", "minimum Home Assistant version")
    equal(hacs["country"], "AT", "country")
    for size in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png"):
        check(
            (base / "custom_components" / "fire_department" / "brand" / size).is_file(),
            f"brand/{size} exists",
        )


def test_geocoding_candidates() -> None:
    print("\n[map] municipality name variants")
    equal(
        geocoding_module.candidates("Stadt Gmünd"),
        ["Gmünd", "Stadt Gmünd"],
        "the 'Stadt' prefix is dropped first",
    )
    check("Zwettl" in geocoding_module.candidates("Zwettl-Stadt"), "'-Stadt' suffix is dropped")
    check(
        "Pyhra" in geocoding_module.candidates("Marktgemeinde Pyhra"),
        "'Marktgemeinde' prefix is dropped",
    )
    check(
        "Großdietmanns" in geocoding_module.candidates("Grossdietmanns"),
        "'ss' fallback covers the umlaut spelling",
    )
    check(
        "GöPFRITZ AN DER WILD" in geocoding_module.candidates("GöPFRITZ AN DER WILD"),
        "mixed case names are used as published",
    )
    check("Seefeld" in geocoding_module.candidates("SEEFELD"), "all caps is title cased")
    check(
        "Weißenkirchen an der Pielach"
        in geocoding_module.candidates("WEISSENKIRCHEN AN DER PIELACH"),
        "connectives stay lower case",
    )
    equal(geocoding_module.candidates("   "), [], "empty name has no variants")
    equal(
        geocoding_module.query_parameters("Musterdorf", const.REGION_NOE)["q"],
        "Musterdorf, Niederösterreich, Austria",
        "query is narrowed to the federal state",
    )
    equal(
        geocoding_module.query_parameters("Musterdorf", "custom")["q"],
        "Musterdorf, Austria",
        "custom sources fall back to Austria",
    )


def geocode_answers() -> dict[str, bytes]:
    """Canned Nominatim responses for every town of the Lower Austria fixtures."""
    documents: dict[str, bytes] = {}
    source = dict(const.SOURCES["noe_active"])
    text = P.decode_bytes(wastl_document("wastl_aktuell.html"), None)
    rows = P.parse_source(text, source, datetime.now(P.TZ))
    for index, row in enumerate(rows):
        town = row.get("municipality")
        if not town:
            continue
        for candidate in geocoding_module.candidates(town):
            params = geocoding_module.query_parameters(candidate, const.REGION_NOE)
            url = f"{geocoding_module.GEOCODE_URL}?{urlencode(params)}"
            documents[url] = json.dumps(
                [{"lat": f"48.1{index}00", "lon": f"15.2{index}00", "display_name": town}]
            ).encode()
    return documents


def test_map_markers() -> None:
    print("\n[map] one marker per running mission")
    fast_geocoding()
    try:
        docs = documents()
        docs.update(geocode_answers())
        hass, entry, ok = ha_stub.run(setup_region(const.REGION_NOE, docs))
        check(ok, "entry set up")
        markers: list = Collector()
        ha_stub.run(geo_location_module.async_setup_entry(hass, entry, markers))
        equal(len(markers), 3, "one marker per running mission")

        async def add_entities() -> None:
            """Home Assistant calls async_added_to_hass when it adds an entity."""
            await asyncio.gather(*(marker.async_added_to_hass() for marker in markers))

        ha_stub.run(add_entities())
        check(all(marker.source == const.SOURCE_MAP_MARKERS for marker in markers), "source attribute")
        check(all(marker.latitude and marker.longitude for marker in markers), "coordinates set")
        check(all(marker.state and marker.state > 0 for marker in markers), "distance from home")
        check(
            all(marker.device_info["identifiers"] == {(const.DOMAIN, entry.entry_id)} for marker in markers),
            "markers belong to the device",
        )
        attributes = markers[0].extra_state_attributes
        equal(attributes["source_kind"], const.KIND_ACTIVE, "source kind attribute")
        check(attributes["municipality"], "municipality attribute")
        check(attributes["type"], "type attribute")
        check(" · " in markers[0].name, "name is keyword and town")

        # a mission finishes -> its marker disappears again
        coordinator = entry.runtime_data
        active_id = const.SOURCES["noe_active"]["id"]
        remaining = coordinator.data[active_id][1:]

        async def push(data: dict) -> None:
            """Update the coordinator and run the tasks its listener scheduled."""
            coordinator.async_set_updated_data(data)
            await asyncio.gather(*hass.tasks)
            hass.tasks.clear()

        ha_stub.run(push({**coordinator.data, active_id: remaining}))
        equal(
            sum(1 for marker in markers if getattr(marker, "removed", False)),
            1,
            "finished mission removes its marker",
        )
        equal(len(markers), 3, "no new marker yet")

        # ... and a new mission adds one
        new_row = dict(remaining[0])
        new_row["id"] = "fixture_new"
        ha_stub.run(push({**coordinator.data, active_id: [new_row] + remaining}))
        equal(len(markers), 4, "new mission adds a marker")
        equal(markers[-1].extra_state_attributes["mission_id"], "fixture_new", "marker id")
    finally:
        restore_geocoding()


def test_map_markers_disabled() -> None:
    print("\n[map] markers switched off")
    options = options_for(const.REGION_NOE)
    options[const.CONF_MAP_MARKERS] = False
    hass = ha_stub.FakeHass(ha_stub.Session(documents()))
    entry = ha_stub.add_entry(hass, title="Test", options=options)
    ok = ha_stub.run(integration.async_setup_entry(hass, entry))
    check(ok, "entry set up")
    markers: list = Collector()
    ha_stub.run(geo_location_module.async_setup_entry(hass, entry, markers))
    equal(len(markers), 0, "no markers without the option")
    check(
        not any("nominatim" in url for url in hass.session.requests),
        "switched off means no external lookup",
    )


def test_map_markers_without_coordinates() -> None:
    print("\n[map] unknown town")
    fast_geocoding()
    try:
        hass, entry, _ = ha_stub.run(setup_region(const.REGION_NOE))
        markers: list = Collector()
        ha_stub.run(geo_location_module.async_setup_entry(hass, entry, markers))
        equal(len(markers), 0, "no marker when the town cannot be resolved")
        check(
            any("nominatim" in url for url in hass.session.requests),
            "the lookup was attempted",
        )
    finally:
        restore_geocoding()


def fast_geocoding() -> None:
    """Drop the one request per second rule for the test run."""
    global _GEOCODE_INTERVAL
    _GEOCODE_INTERVAL = geocoding_module.GEOCODE_MIN_INTERVAL
    geocoding_module.GEOCODE_MIN_INTERVAL = 0


def restore_geocoding() -> None:
    """Restore the Nominatim throttle."""
    geocoding_module.GEOCODE_MIN_INTERVAL = _GEOCODE_INTERVAL


_GEOCODE_INTERVAL = 1.1


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("\n" + "=" * 60)
    if FAILURES:
        print(f"{len(FAILURES)} FAILED CHECK(S):")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print(f"all {len(tests)} test functions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

