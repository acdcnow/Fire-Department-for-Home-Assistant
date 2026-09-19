# Changelog

All notable changes to this project are documented in this file.
Tags in this repository have no `v` prefix.

## 3.0.0-beta.1 - 2026-09-19

Home Assistant 2026.9 base, three federal states, new data model.
**Breaking:** requires Home Assistant 2026.9+, `data_list` is replaced by `incidents`.

### Added

* **Upper Austria** support: running missions, deployed brigades (derived from the
  mission list) and the last 24 hours from `einsaetze.ooelfv.at`, including district
  code/name, the colour chip of the source and the per-brigade times.
* **Styria** support: running and finished missions from the public list of the
  LFV Steiermark (delimited data, 24 h window, `assigned_units` drives the state).
* **Colour option**: `color` on every row and a `color_legend` attribute, selectable
  per entry (`severity`, `category`, `source`, `source_color`, `none`).
* **Category filter** option (`fire`, `technical`, `hazardous`, `exercise`, `special`,
  `other`).
* **`Operations running` binary sensor** (`device_class: safety`) per active source.
* **Automation events** `fire_department_new_incident` and
  `fire_department_incident_closed`.
* **Diagnostics** support and **brand icons** (`custom_components/fire_department/brand`).
* **Custom sources** can be added in the options (four parsers to choose from).
* New attributes: `latest_incident`, `longest_running`, `average_duration`,
  `by_category`, `by_district`, `by_keyword`, `brigades`, `truncated`, `source_*`,
  `fetched_at`, `last_error`.
* `tests/` with a Home Assistant stub, fixtures and ~350 assertions - runnable with a
  plain Python interpreter, plus live validation of the real pages.

### Changed

* Requires **Home Assistant 2026.9 or newer**; `ConfigFlowResult`, `entry.runtime_data`,
  `DeviceInfo` from `homeassistant.helpers.device_registry`, `asyncio.timeout`.
* **No Python requirements** any more (a small stdlib HTML parser replaces
  BeautifulSoup), so nothing is installed during setup.
* All three sensors of a state are one device, with working documentation and issue
  tracker links.
* Config flow stores everything in options, sets a unique id per federal state and
  only offers regions that really have a source.
* Options flow rewritten: `general`, `sources`, `add_page`, `remove_page`, every change
  saves and **reloads** the integration; translations for every step and abort reason.
* Interval default 30 minutes, minimum 5 (was 60/15), number of missions kept in the
  attributes is configurable (default 25, `0` = counts only).

### Fixed

* `manifest.json` documentation/issue tracker pointed to the non existing
  `acdcnow/fire-department`.
* WASTL columns are labelled correctly (`station` = control centre, `municipality`,
  `type`) instead of calling the control centre a district.
* The WASTL brigade number is kept (`brigade_code`, e.g. `140302`).
* ÖO end times without a date (`19.09. 15:10 – 15:34`) are parsed, so durations work.
* Relative WASTL timestamps (`< 1 std.`) are no longer mistaken for real times.
* `aiohttp.ClientSession` is no longer created per entry (and never closed);
  the Home Assistant shared session is used.
* `async_timeout` removed - it is not a Home Assistant dependency any more.
* Data is stored in `entry.runtime_data` instead of `hass.data`.
* `add_page` / `remove_page` and the `no_pages` abort are translated.
* Config entries can no longer be created twice for the same federal state.
* Existing 1.x/2.x entries are migrated automatically.

### Migration

* Update the integration, restart Home Assistant - the config entry is migrated on the
  first start and reloads itself.
* Replace `data_list` with `incidents` in your own dashboards (the shipped dashboard
  files are updated). `row[0]` becomes `mission.date`, `row[4]` becomes `mission.type`.

## 2.2.0

* Lower Austria (WASTL) with active operations, deployed brigades and history.
* First release with translations and dashboards.
