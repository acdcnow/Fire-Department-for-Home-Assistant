# Feuerwehr Österreich · Pro dashboard

A complete, ready-to-paste Lovelace dashboard for **Fire Department Austria 3.x**,
plus the map markers that make the built-in Home Assistant map show the current
situation.

> UI labels are German because the sources are German (`Einsatzart`, `Gemeinde`,
> `Alarmzentrale`). Rename them freely.

---

## 1. What you get

| View | Content |
| :--- | :--- |
| **Leitstelle** | KPI tiles (running missions, brigades, finished 24 h), live map, group bars by *Einsatzart* and *Bezirk*, colour legend + data freshness, newest missions |
| **Laufende Einsätze** | Full table: search, sortable headers, colour-coded alarm badges, row counter, unit count |
| **Feuerwehren** | One row per brigade and mission (with the brigade number of the source) |
| **Historie** | 24 h graph of all sensors + table of finished missions with duration |
| **Karte** | Large marker map + WASTL's own map and plain OpenStreetMap as iframe fallbacks |

Every view works for **one or several federal states at once** - the numbers on the
overview are summed over all configured entries.

## 2. Requirements

| Card | Needed for | Where |
| :--- | :--- | :--- |
| `custom:flex-table-card` | all tables | HACS frontend |
| `custom:auto-entities` | finding the sensors automatically | HACS frontend |
| `custom:mushroom-template-card` | KPI tiles | HACS frontend |
| `card-mod` | only cosmetic tweaks | HACS frontend |

Everything else is built in: `map`, `history-graph`, `iframe`, `markdown`.

## 3. Installation

1. Settings → Dashboards → **+ Add dashboard** → *New dashboard from scratch*
   → title `Feuerwehr Österreich` → create → open it.
2. Top-right menu → **Edit dashboard** → **Raw configuration editor**
   → paste the content of `fire_department_pro.yaml` → **Save**.

As a YAML dashboard instead:

```yaml
# configuration.yaml
lovelace:
  dashboards:
    feuerwehr:
      mode: yaml
      title: Feuerwehr Österreich
      icon: mdi:fire-station
      show_in_sidebar: true
      filename: dashboards/fire_department.yaml
```

## 4. Why no entity ids appear in the file

Entity ids depend on the language and on the name you gave the entry, and there can be
one entry per federal state. The dashboard therefore never hard-codes them - it selects
the sensors by their attributes:

```yaml
filter:
  include:
    - attributes:
        source_kind: active_operations     # or deployed_fire_brigade / completed_missions
```

`source_kind` is one of the attributes added in 3.0.0 for exactly this purpose. The
tables read the mission list from `incidents` (list of mission dictionaries) and reach
into each row with `modify: x.<key>`.

## 5. Cards used and why

| Requirement | Card | Reason |
| :--- | :--- | :--- |
| Big numbers | `mushroom-template-card` in a `grid` | readable at a glance, sums over all entries |
| Table with search/sort | `flex-table-card` | sortable headers, live search, row footer, hundreds of rows |
| Colour-coded alarm | `modify:` (JS) inside a flex-table column | cells are rendered as HTML, so the badge takes the `color` attribute of the mission |
| Group bars | `markdown` + Jinja | uses the `by_category` / `by_district` counters the integration already computes - no extra template sensors |
| Trend | `history-graph` | the sensors have no `unit_of_measurement`, so `statistics-graph` would stay empty |
| Map | built-in `map` | free OSM tiles via `map_tiles`, clustering, no API key |
| External maps | `iframe` | WASTL's own map, or plain OpenStreetMap as a fallback |

## 6. How to display the groups

1. **By kind** - one view per sensor kind (this dashboard). Native, fast, works on
   mobile; the tab bar is the group switcher.
2. **By alarm keyword** - the `Alarm` badge column shows `B1`, `T03V`, `SOF1`, …
   coloured with the mission colour; clicking the header groups them.
3. **By place** - the *Nach Bezirk* bars answer "where is it busy right now?", the
   `Gemeinde` column groups the table, and the search box filters live (e.g. `Zwettl`).
4. **By mission type** - the *Nach Einsatzart* bars, or the integration's *Mission
   types* filter if you only ever want to see fires.
5. **By federal state** - the `Bundesland` column, plus the summed tiles on the
   overview.

## 7. The map

```yaml
type: map
geo_location_sources:
  - source: fire_department
    label_mode: name      # name | state | attribute | icon
auto_fit: true
```

* Every **running mission** is a `geo_location` entity, named `Alarm · Gemeinde`.
* Position = **centre of the municipality**. The mission lists publish no coordinates,
  so the town is looked up once at OpenStreetMap and cached; markers without a
  resolvable town are simply left out.
* Marker state = **distance from home in metres** (`label_mode: state`),
  `label_mode: attribute` with `attribute: type` puts the mission type on the map.
* Markers disappear as soon as a mission is finished.
* Tiles: since **Home Assistant 2026.9** the `map_tiles` system integration serves the
  base map - it proxies the OpenStreetMap tiles through your own instance behind a
  rotating token and caches them. No API key, no request from your browser to a third
  party.

### Privacy

Lookups go to `nominatim.openstreetmap.org`, are throttled to one request per second and
cached permanently (including "not found") in `.storage/fire_department_geocoding`.
After the first few days it is effectively offline. Turn it off completely in
**Configure → General settings → Map markers**; the map then stays empty and the
iframes remain.

## 8. Troubleshooting

| Symptom | Cause / fix |
| :--- | :--- |
| Table is shorter than the sensor state | The sensors expose at most *Missions in the attributes* rows (25 by default) - raise it in *General settings* (0 = counts only) |
| "no entities" in a table | `flex-table-card`/`auto-entities` not installed, or the attribute filter matches nothing (check Developer tools → States) |
| Empty cells | flex-table-card older than 1.4.0 - update via HACS |
| No map markers | Map markers switched off, no internet, or the town is unknown to OpenStreetMap (check the log with `custom_components.fire_department` at debug level) |
| Marker in the wrong place | The town name is ambiguous - add the correct name to `geocoding.py` or clear the entry in `.storage/fire_department_geocoding` |
| KPI tile shows `0` | Entry not set up yet, or all its sensors are unavailable (see *Datenstand* card for the last error) |
