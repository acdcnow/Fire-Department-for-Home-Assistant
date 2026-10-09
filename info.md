# Fire Department Austria

Show **current fire department missions in Austria** in Home Assistant - live missions,
deployed brigades and the mission history of the last 24 hours.

**Highlights**

* Real-time mission lists for **Lower Austria (WASTL)**, **Upper Austria** and **Styria**
* Running missions, deployed fire brigades and mission history as sensors, plus a
  `Operations running` binary sensor for automations
* Automation events `fire_department_new_incident` and `fire_department_incident_closed`
* Colour option: every mission carries a colour - by severity, mission type, federal
  state or the colour of the source page
* Category filter (fire, technical, hazardous goods, exercise, special)
* Rich attributes: town, district, alert keyword `B1`/`T1`, severity, involved brigades,
  duration and `by_category` / `by_district` / `brigades` counters
* Everything configurable in the UI, options reload the integration automatically
* Diagnostics support, one device per federal state, brand icon included
* No Python dependencies, Home Assistant 2026.9 or newer

**Supported regions**

| State | Running missions | Brigades | History |
| --- | --- | --- | --- |
| Lower Austria (WASTL) | ✅ | ✅ | ✅ |
| Upper Austria (LFV OÖ) | ✅ | ✅ | ✅ |
| Styria (LFV Steiermark) | ✅ | ✅ | ✅ |

Vienna, Salzburg, Carinthia, Burgenland, Tyrol and Vorarlberg do not publish a
machine readable mission list yet - the README lists the candidate pages and custom
sources can be added in the options.
**[Documentation wiki](https://github.com/acdcnow/fire-department-for-Home-Assistant/wiki)** ·
[README](https://github.com/acdcnow/fire-department-for-Home-Assistant/blob/HA2026_09_dev/README.md) ·
[Changelog](https://github.com/acdcnow/fire-department-for-Home-Assistant/blob/HA2026_09_dev/CHANGELOG.md)
Unofficial project, not affiliated with any fire brigade or fire brigade association.
