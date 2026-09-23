"""Constants for the Fire Department integration."""
from datetime import timedelta

DOMAIN = "fire_department"
CONF_PAGES = "pages"
CONF_REGION = "region"
CONF_UPDATE_INTERVAL = "update_interval"

# Parser Types
TYPE_INCIDENTS = "incidents"       # For Current/Historic (4+ cols)
TYPE_DEPARTMENTS = "departments"   # For Active FF (3 cols)

DEFAULT_NAME = "Fire Department Info"
DEFAULT_UPDATE_INTERVAL = 60 # Minutes

# Sensor Keys (Used for translation lookups)
KEY_ACTIVE_OPS = "active_operations"
KEY_DEPLOYED_FF = "deployed_fire_brigade"
KEY_COMPLETED = "completed_missions"

# Layout of every row inside the 'data_list' attribute
# [Datum, Zeit, Alarmzentrale/Feuerwehr, Gemeinde, Einsatzart]
ROW_DATE = 0
ROW_TIME = 1
ROW_CENTER = 2
ROW_PLACE = 3
ROW_KIND = 4

# geo_location / map support
# Value of the 'source' attribute of the map markers, referenced by
# geo_location_sources inside the map card of the dashboard.
SOURCE = DOMAIN
# Set to False for a fully offline installation - no map markers are created.
GEOCODE_ENABLED = True
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
GEOCODE_REGION = "Niederösterreich, Austria"
GEOCODE_USER_AGENT = (
    "HomeAssistant-FireDepartment/2.3 "
    "(+https://github.com/acdcnow/Fire-Department-for-Home-Assistant)"
)
# Nominatim usage policy: at most one request per second.
GEOCODE_MIN_INTERVAL = 1.1
GEOCODE_STORAGE_KEY = f"{DOMAIN}_geocoding"
GEOCODE_STORAGE_VERSION = 1

PARSER_TYPES = {
    TYPE_INCIDENTS: "Incidents List (Current/History)",
    TYPE_DEPARTMENTS: "Active Departments List",
}

# Catalog of Regions
CATALOG = {
    "lower_austria": [
        {
            "name": KEY_ACTIVE_OPS,
            "url": "https://www.feuerwehr-krems.at/codepages/wastl/wastlmain/Land_EinsatzAktuell.asp",
            "type": TYPE_INCIDENTS
        },
        {
            "name": KEY_DEPLOYED_FF,
            "url": "https://www.feuerwehr-krems.at/codepages/wastl/wastlmain/Land_FFimEinsatz.asp",
            "type": TYPE_DEPARTMENTS
        },
        {
            "name": KEY_COMPLETED,
            "url": "https://www.feuerwehr-krems.at/CodePages/Wastl/WastlMain/Land_EinsatzHistorie.asp",
            "type": TYPE_INCIDENTS
        }
    ],
    "vienna": [],
    "upper_austria": [],
    "styria": [],
    "salzburg": [],
    "burgenland": [],
    "carinthia": [],
    "tyrol": [],
    "vorarlberg": []
}
