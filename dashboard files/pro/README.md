# Feuerwehr NÖ · Pro dashboard

A ready-to-paste Lovelace dashboard for the *Fire Department Info* integration,
plus the map markers that make the built-in Home Assistant map work.

> UI labels are German because the WASTL source data is German
> (`Einsatzart`, `Gemeinde`, `Alarmzentrale`). Rename them freely.

---

## 1. What you get

| View | Content |
| :--- | :--- |
| **Leitstelle** | KPI tiles (active operations / brigades / completed), live map, group breakdown by *Einsatzart* and *Top-Gemeinden*, the 6 newest operations, data-source freshness |
| **Aktive Einsätze** | Full table: searchable, sortable, colour-coded category badges, row-count footer |
| **Feuerwehren im Einsatz** | One row per brigade and operation |
| **Historie** | 48 h history graph of all sensors + table of the completed operations |
| **Karte** | Large marker map + two iframe fallbacks (WASTL's own map, plain OpenStreetMap) |

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
   → title `Feuerwehr NÖ` → create → open it.
2. Top-right menu → **Edit dashboard** → **Raw configuration editor**
   → paste the content of `fire_department_pro.yaml` → **Save**.

As a YAML dashboard instead:

```yaml
# configuration.yaml
lovelace:
  dashboards:
    feuerwehr:
      mode: yaml
      title: Feuerwehr NÖ
      icon: mdi:fire-station
      show_in_sidebar: true
      filename: dashboards/fire_department.yaml
```

## 4. How the integration data looks (verified against the live pages)

Every sensor carries the raw parsed rows in the `data_list` attribute:

| Index | Active operations / history | Deployed brigades |
| :--- | :--- | :--- |
| `0` | `23.09.2026` (date) | date |
| `1` | `< 1 std.` / `21:09:00` (time) | time |
| `2` | `Alarmzentrale` or `BAZ Krems/Donau` | **brigade** (`Eichberg`) |
| `3` | **municipality** (`Grossdietmanns`) | `-` |
| `4` | **Einsatzart** (`T1 Bergung - PKW`) | Einsatzart |

Sensors created by the integration (region *Lower Austria*):

| Sensor | Meaning |
| :--- | :--- |
| `sensor.<name>_active_operations` / `..._aktuelle_einsatze` | number of current operations |
| `sensor.<name>_deployed_fire_brigade` / `..._eingesetzte_feuerwehren` | number of deployed brigades |
| `sensor.<name>_completed_missions` / `..._beendete_einsatze` | number of finished operations (rolling window of the source, currently 100 rows) |
| `geo_location.*` | one map marker per active operation (new) |

**Entity IDs are language dependent** (they follow the translated entity name).
That is why the dashboard never hard-codes them: `auto-entities` selects the
sensors by their attributes instead.

```yaml
filter:
  include:
    - attributes:
        data_list: '$$*'          # sensor has a parsed table
        url: '/Land_EinsatzAktuell/'   # ... and it is this page
```

## 5. Cards used and why

| Requirement | Card | Reason |
| :--- | :--- | :--- |
| Big numbers | `mushroom-template-card` in a `grid` | readable at a glance, template driven |
| Table with search/sort | `flex-table-card` | sortable headers, live search, 1000+ rows, row footer; `data_list` is a *list of lists*, which `flex-table-card` expands row-wise when every column selects the same array with `data: data_list` + `modify: x[n]` |
| Colour-coded category | `modify:` (JS) inside a flex-table column | cells are rendered as HTML, so a styled `<span>` badge works |
| Group breakdown | `markdown` + Jinja | no extra template sensors needed, recomputed on every state change |
| Trend | `history-graph` | sensor state = number of rows; works without `state_unit`/long-term statistics (so **not** `statistics-graph`) |
| Map | built-in `map` | free OSM tiles via `map_tiles`, clustering, no API key |
| External maps | `iframe` | WASTL's own map, or plain OSM as a fallback |

## 6. How to display the groups

1. **By sensor** – one view per group (this dashboard). Native, fast, works on
   mobile; the tab bar is the "group switcher".
2. **By category (B / T / S / SOF / U)** – the `Kat.` badge column plus the
   *Nach Einsatzart* bars. Clicking the `Kat.` header groups all rows of the
   same category together.
3. **By place** – the *Top-Gemeinden* bars answer "where is it burning right
   now?"; clicking the `Gemeinde` or `Alarmzentrale` header groups the table, and
   the search box filters live (e.g. `Zwettl`).
4. **By time** – the table is already in source order (newest first); the
   history graph covers the long-term view.

Everything else (real grouped sub-tables per category/district) would need one
entity per group, which the integration does not create – the row attribute can
not be split by Lovelace cards. `sort_by` in `flex-table-card` +
`enable_search: true` is the pragmatic equivalent.

## 7. The map

Three options, all free:

1. **Built-in map card (recommended)** – uses the markers of the integration:

   ```yaml
   type: map
   geo_location_sources:
     - source: fire_department
       label_mode: name      # label_mode: name | state | attribute | icon
   auto_fit: true
   ```

   * Tiles: since **Home Assistant 2026.9** the system integration
     **`map_tiles`** serves the map. It proxies the OpenStreetMap vector tiles
     (`vector.openstreetmap.org`) through your own instance behind a rotating
     access token and caches up to 32 MB in memory. No API key, no external
     frontend request - the browser only talks to your HA instance.
   * Markers: one `geo_location` entity per active operation, named
     `Einsatzart · Gemeinde`, state = distance from home in metres.
   * Position: the **centre of the municipality**. WASTL does not publish
     coordinates, so the integration looks the municipality up in OpenStreetMap
     and caches the result permanently.

2. **WASTL's own map** (`https://www.feuerwehr-krems.at/CodePages/Wastl/wastlmain/ShowOverview.asp`)
   as an `iframe` - the source's operational map, no coordinates needed.

3. **Plain OpenStreetMap embed** as an `iframe`. Free and key-free, but the OSM
   embed can only show **one** marker - that is why it is used as a region map:

   ```
   https://www.openstreetmap.org/export/embed.html?bbox=14.40,47.40,17.10,49.05&layer=mapnik
   ```

### Privacy / offline

The geocoding asks `nominatim.openstreetmap.org` for municipality names that are
not in the cache yet (throttled to one request per second, cached in
`.storage/fire_department_geocoding`, also for "not found"). After the first few
days it is effectively offline. To switch it off completely, set
`GEOCODE_ENABLED = False` in `custom_components/fire_department/const.py` -
the dashboard then simply shows no markers and the iframes remain.

## 8. Troubleshooting

| Symptom | Cause / fix |
| :--- | :--- |
| Table says *no entities* | `flex-table-card` not installed, or the entity was renamed so the `url` filter no longer matches |
| Empty table cells | flex-table older than 1.4.0 - update via HACS |
| No map markers | Geocoding disabled/offline, or the municipality is unknown; check the log (`debug` for `custom_components.fire_department`) |
| Markers in the wrong place | the source name is ambiguous - add the correct name to `geocoding.py` / clear the cache entry in `.storage/fire_department_geocoding` |
| KPI tile shows `–` | the integration is not set up or is still loading |
