# Dashboard files

Ready to paste cards for the Fire Department Austria integration. Copy the content of
a file into a blank dashboard (raw configuration editor) or into a **Manual card**.

Adjust the entity ids if your entry is not named `Fire Department`:

| Card | Default entity |
| --- | --- |
| Running missions | `sensor.fire_department_active_operations` |
| Deployed brigades | `sensor.fire_department_deployed_fire_brigades` |
| Mission history | `sensor.fire_department_completed_missions` |
| Missions running | `binary_sensor.fire_department_operations_running` |

With a German Home Assistant the entity names are e.g.
`sensor.feuerwehr_aktuelle_einsatze` - check **Developer tools → States** for yours.

All rows are colour coded through the `color` attribute of every mission, which depends
on the colour scheme selected in the integration options.

## Ready made dashboard (recommended)

The [`pro`](pro/README.md) folder contains a complete dashboard instead of single cards:
KPI tiles, live map with mission markers, group bars, searchable and sortable tables and
a large map view. It does **not** hard-code any entity id, so nothing has to be adjusted
for your language, your entry name or the number of federal states.
