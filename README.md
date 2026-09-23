# Fire Department Info (Austria)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/badge/version-2.3.0-blue.svg)]()
[![Maintainer](https://img.shields.io/badge/maintainer-acdcnow-orange.svg)]()

A Home Assistant integration that retrieves fire department operations and incident data for Austria. It primarily scrapes the "WASTL" (Warn- und Alarmsystem) information to provide real-time updates on active incidents, deployed fire brigades, and completed missions.

## Features

* **Real-time Incident Monitoring**: View active fire department operations.
* **Detailed Attributes**: Access lists of specific incidents, locations, and timestamps via attributes.
* **Configurable**: Set your preferred update interval and region via the UI.
* **Sensor Types**:
    * **Active Operations**: Count of currently ongoing incidents.
    * **Deployed Fire Brigades**: Count of fire brigades currently deployed.
    * **Completed Missions**: Count of missions completed (history).
* **Map markers**: every active operation is exposed as a `geo_location`
  entity, so the built-in Home Assistant map card shows them without any
  additional integration (municipality centre from OpenStreetMap, distance from
  home as state).
* **Ready-made dashboard**: a full professional Lovelace dashboard with KPIs,
  searchable/sortable tables, group breakdowns and maps - see
  [`dashboard files/pro`](dashboard%20files/pro/README.md).

## Supported Regions

Currently, the following regions are selectable, but **data sources are fully configured for**:

* **Lower Austria (Niederösterreich)** ✅

*Other regions (Vienna, Upper Austria, Styria, etc.) are present in the configuration for future expansion but do not yet have active data URLs defined.*

## Installation

### Option 1: HACS (Recommended)

1.  Open HACS in your Home Assistant instance.
2.  Go to **Integrations** > click the **3 dots** (top right) > **Custom repositories**.
3.  Add the URL of this repository.
4.  Category: **Integration**.
5.  Click **Add** and then **Download**.
6.  Restart Home Assistant.

### Option 2: Manual

1.  Download the `custom_components/fire_department` folder from this repository.
2.  Copy the folder into your Home Assistant's `config/custom_components/` directory.
3.  Restart Home Assistant.

## Configuration

1.  Go to **Settings** > **Devices & Services**.
2.  Click **+ Add Integration**.
3.  Search for **Fire Department Info**.
4.  Follow the setup wizard:
    * **Name**: Give your integration a custom name (default: Fire Department Info).
    * **Region**: Select your Austrian federal state (e.g., Lower Austria).
    * **Update Interval**: Set how often data should be fetched (minutes).

### Options

You can change settings later by clicking **Configure** on the integration entry:
* Change the update interval.
* Add or remove specific pages/sensors manually if needed.

## Sensors

The integration creates the following sensors (entity IDs depend on your configuration name):

| Sensor Name | ID Example | Description |
| :--- | :--- | :--- |
| **Active Operations** | `sensor.fire_department_info_active_operations` | Number of current incidents. |
| **Deployed Fire Brigades** | `sensor.fire_department_info_deployed_fire_brigades` | Number of brigades currently in action. |
| **Completed Missions** | `sensor.fire_department_info_completed_missions` | Number of missions finished recently. |
| **Map markers** | `geo_location.t1_bergung_pkw_weinburg` | One entity per active operation (`source: fire_department`), position = centre of the municipality. |

**Note:** the entity IDs are derived from the translated entity names, so they
follow your Home Assistant language (`..._aktuelle_einsatze` in German,
`..._active_operations` in English) and your custom integration name. Dashboards
should therefore not hard-code them - the
[pro dashboard](dashboard%20files/pro/README.md) selects the sensors by their
attributes instead.

## Dashboards

There are two sets of dashboard files:

* `dashboard files/` - the original single-card examples (`active_operations.yaml`,
  `deployed_brigades.yaml`, `completed_missions.yaml`, `operational_Overview.yaml`).
  Copy the YAML into a blank dashboard and adjust the sensor names.
* `dashboard files/pro/` - **recommended**: a complete, ready-to-paste dashboard
  (`fire_department_pro.yaml`) with 5 views, KPI tiles, searchable and sortable
  tables, colour-coded categories, group breakdowns and three map options.
  It works without touching entity IDs. See its
  [README](dashboard%20files/pro/README.md).

## Map

WASTL does not publish coordinates, so the integration resolves the municipality
of every active operation to the centre of that municipality and creates a
`geo_location` entity for it. The built-in map card then only needs:

```yaml
type: map
geo_location_sources:
  - source: fire_department
    label_mode: name     # name | state | attribute | icon
auto_fit: true
```

* Tiles are served by the **`map_tiles` system integration** introduced in
  Home Assistant 2026.9: it proxies the OpenStreetMap tiles through your own
  instance behind a token and caches them (no API key, no third-party request
  from the browser).
* The marker state is the **distance from home in metres**, the label is
  `Einsatzart · Gemeinde`.
* Alternatives without markers: WASTL's own overview map or a plain
  OpenStreetMap embed as an `iframe` (both are part of the pro dashboard).

### Geocoding / privacy

Municipalities that are not cached yet are looked up at
`nominatim.openstreetmap.org` - throttled to one request per second and cached
permanently (including negative results) in `.storage/fire_department_geocoding`.
After the first few days it is effectively offline. For a fully offline
installation set `GEOCODE_ENABLED = False` in
`custom_components/fire_department/const.py`; the map then simply stays empty.

### Attributes
Each sensor contains a `data_list` attribute with the raw parsed rows, useful for displaying in Markdown cards or Flex Table cards.

**`data_list` structure** (verified against the live Lower Austria pages):
```json
[
  ["23.09.2026", "< 1 std.", "Alarmzentrale", "Grossdietmanns", "S1 Geruch - Schadstoff/Gas"],
  ["23.09.2026", "21:09:00", "BAZ Krems/Donau", "Weitra", "T1 Bergung - PKW"]
]
```

| Index | Active operations / history | Deployed brigades |
| :--- | :--- | :--- |
| `0` | date (`DD.MM.YYYY`) | date |
| `1` | time (relative `< 1 std.` / absolute `21:09:00`) | time |
| `2` | alerting centre (`Alarmzentrale`, `BAZ Krems/Donau`) | fire brigade (number prefix removed) |
| `3` | municipality | `-` |
| `4` | operation type (`T1 Bergung - PKW`) | operation type |
