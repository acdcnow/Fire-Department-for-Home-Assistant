"""A very small Home Assistant stand-in so the integration can be tested.

Only the pieces the fire_department integration touches are implemented.  The
goal is to run ``async_setup_entry``, the config flow, the coordinators and the
entities of a plain Python interpreter.
"""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import timedelta
from typing import Any, Generic, TypeVar


# --------------------------------------------------------------------------- #
# module helpers
# --------------------------------------------------------------------------- #
def _module(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


def _attr(module: types.ModuleType, **values: Any) -> types.ModuleType:
    for key, value in values.items():
        setattr(module, key, value)
    return module


class HomeAssistantError(Exception):
    """Stand-in for homeassistant.exceptions.HomeAssistantError."""


def callback(func):
    """Stand-in for homeassistant.core.callback."""
    return func


# --------------------------------------------------------------------------- #
# const / core / exceptions
# --------------------------------------------------------------------------- #
const = _attr(
    _module("homeassistant.const"),
    Platform=types.SimpleNamespace(
        SENSOR="sensor", BINARY_SENSOR="binary_sensor", GEO_LOCATION="geo_location"
    ),
)
core = _module("homeassistant.core")
core.callback = callback
core.HomeAssistant = object
core.ServiceCall = object
exceptions = _attr(_module("homeassistant.exceptions"), HomeAssistantError=HomeAssistantError)


# --------------------------------------------------------------------------- #
# util.dt
# --------------------------------------------------------------------------- #
class _Dt:
    @staticmethod
    def utcnow():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)

    @staticmethod
    def now(tz=None):
        from datetime import datetime

        return datetime.now(tz)


util = _module("homeassistant.util")
util.dt = _attr(_module("homeassistant.util.dt"), **{"utcnow": _Dt.utcnow, "now": _Dt.now})


class _Location:
    """Stand-in for homeassistant.util.location."""

    @staticmethod
    def distance(lat1, lon1, lat2, lon2):
        """Great circle distance in metres, ``None`` if a value is missing."""
        if None in (lat1, lon1, lat2, lon2):
            return None
        from math import asin, cos, radians, sin, sqrt

        lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
        part = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
        return 6371000 * 2 * asin(sqrt(part))


util.location = _attr(_module("homeassistant.util.location"), distance=_Location.distance)


# --------------------------------------------------------------------------- #
# config_entries
# --------------------------------------------------------------------------- #
class ConfigEntry:
    """Minimal config entry."""

    def __init__(self, entry_id="test_entry", title="Test", data=None, options=None, version=2, minor_version=1):
        self.entry_id = entry_id
        self.title = title
        self.data = data or {}
        self.options = options or {}
        self.version = version
        self.minor_version = minor_version
        self.domain = "fire_department"
        self.state = "loaded"
        self.runtime_data = None
        self._listeners = []
        self._async_on_unload = []

    def async_on_unload(self, func):
        self._async_on_unload.append(func)

    def add_update_listener(self, func):
        self._listeners.append(func)
        return lambda: None


ConfigFlowResult = dict


class FlowResult(dict):
    """Stand-in for the flow result dict."""


class ConfigFlow:
    """Minimal config flow base class."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()

    def __init__(self, handler=None, hass=None):
        self.handler = handler
        self.hass = hass
        self.unique_id = None

    async def async_set_unique_id(self, unique_id, raise_on_progress=True):
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self, updates=None, *, reload_on_update=True):
        if self.hass and self.unique_id in getattr(self.hass.config_entries, "unique_ids", set()):
            raise _AbortFlow("already_configured")

    @callback
    def async_show_form(self, *, step_id, data_schema=None, errors=None, description_placeholders=None, last_step=None, **kwargs):
        return {"type": "form", "step_id": step_id, "data_schema": data_schema, "errors": errors or {}}

    @callback
    def async_show_menu(self, *, step_id, menu_options, description_placeholders=None, **kwargs):
        return {"type": "menu", "step_id": step_id, "menu_options": list(menu_options)}

    @callback
    def async_create_entry(self, *, title, data, description=None, description_placeholders=None, next_flow=None, options=None, subentries=None, **kwargs):
        return {
            "type": "create_entry",
            "title": title,
            "data": data,
            "options": options or {},
            "version": getattr(self, "VERSION", 1),
            "minor_version": getattr(self, "MINOR_VERSION", 0),
        }

    @callback
    def async_abort(self, *, reason, description_placeholders=None, **kwargs):
        return {"type": "abort", "reason": reason}


class _AbortFlow(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class AbortFlow(_AbortFlow):
    """Public alias so tests can catch the abort."""


AbortFlow = _AbortFlow  # noqa: F811 - exported for the tests


class OptionsFlow:
    """Minimal options flow base class."""

    handler: str | None = None

    @property
    def config_entry(self) -> ConfigEntry:
        if self.hass is None:
            raise ValueError("config_entry is not available during initialisation")
        return self.hass.config_entries.async_get_known_entry(self.handler)

    def __init__(self, hass=None, handler=None):
        self.hass = hass
        self.handler = handler

    @callback
    def async_show_form(self, **kwargs):
        return ConfigFlow.async_show_form(self, **kwargs)

    @callback
    def async_show_menu(self, **kwargs):
        return ConfigFlow.async_show_menu(self, **kwargs)

    @callback
    def async_create_entry(self, *, title=None, data, description=None, description_placeholders=None, unique_id=None, **kwargs):
        return {"type": "create_entry", "title": title, "data": data, "options": data}

    @callback
    def async_abort(self, **kwargs):
        return ConfigFlow.async_abort(self, **kwargs)


class ConfigEntryState:
    LOADED = "loaded"


config_entries = _attr(
    _module("homeassistant.config_entries"),
    ConfigEntry=ConfigEntry,
    ConfigFlow=ConfigFlow,
    ConfigFlowResult=ConfigFlowResult,
    ConfigEntryState=ConfigEntryState,
    OptionsFlow=OptionsFlow,
    FlowResult=FlowResult,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
helpers = _module("homeassistant.helpers")


class SelectorMode:
    DROPDOWN = "dropdown"
    LIST = "list"
    BOX = "box"


class SelectSelectorConfig(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)


class SelectSelector:
    def __init__(self, config):
        self.config = config

    def __call__(self, value):
        return value


class NumberSelectorConfig(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)


class NumberSelector:
    def __init__(self, config):
        self.config = config

    def __call__(self, value):
        return value


selector = _attr(
    _module("homeassistant.helpers.selector"),
    SelectSelector=SelectSelector,
    SelectSelectorConfig=SelectSelectorConfig,
    SelectSelectorMode=SelectorMode,
    NumberSelector=NumberSelector,
    NumberSelectorConfig=NumberSelectorConfig,
    NumberSelectorMode=SelectorMode,
)


class DeviceEntryType:
    SERVICE = "service"
    DEVICE = "device"


class DeviceInfo(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


device_registry = _attr(
    _module("homeassistant.helpers.device_registry"),
    DeviceInfo=DeviceInfo,
    DeviceEntryType=DeviceEntryType,
)


def async_get_clientsession(hass):
    return hass.session


class Session:
    """Tiny aiohttp stand-in returning canned documents."""

    def __init__(self, documents: dict[str, bytes], charsets: dict[str, str] | None = None):
        self.documents = documents
        self.charsets = charsets or {}
        self.requests: list[str] = []

    def get(self, url, **kwargs):
        params = kwargs.get("params")
        if params:
            from urllib.parse import urlencode

            url = f"{url}?{urlencode(params)}"
        self.requests.append(url)
        return _ResponseContext(self, url)


class _Response:
    def __init__(self, session: Session, url: str):
        self.url = url
        self._session = session
        if url not in session.documents:
            self.status = 404
            self.headers = {"Content-Type": "text/html"}
            self._body = b"not found"
        else:
            self.status = 200
            charset = session.charsets.get(url, "")
            self.headers = {"Content-Type": f"text/html; charset={charset}" if charset else "text/html"}
            self._body = session.documents[url]

    async def read(self) -> bytes:
        return self._body

    async def json(self, content_type=None, **kwargs):
        import json

        return json.loads(self._body.decode("utf-8"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _ResponseContext:
    def __init__(self, session: Session, url: str):
        self._response = _Response(session, url)

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc):
        return False


aiohttp_client = _attr(_module("homeassistant.helpers.aiohttp_client"), async_get_clientsession=async_get_clientsession)


class UpdateFailed(HomeAssistantError):
    """Stand-in for homeassistant.helpers.update_coordinator.UpdateFailed."""


_DataT = TypeVar("_DataT")


class DataUpdateCoordinator(Generic[_DataT]):
    """Minimal coordinator with the parts the integration uses."""

    def __init__(self, hass, logger, *, name, update_interval=None, config_entry=None, **kwargs):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.config_entry = config_entry
        self.data = None
        self.last_update_success = True
        self.update_count = 0
        self._listeners: list = []

    async def _async_update_data(self):  # pragma: no cover - overridden
        raise NotImplementedError

    async def async_config_entry_first_refresh(self):
        await self.async_refresh()

    async def async_refresh(self):
        try:
            self.data = await self._async_update_data()
            self.last_update_success = True
        except UpdateFailed:
            self.last_update_success = False
            raise
        self.update_count += 1
        self._notify_listeners()
        return self.data

    def async_add_listener(self, update_callback, context=None):
        self._listeners.append(update_callback)

        def remove_listener():
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    def _notify_listeners(self):
        for listener in list(self._listeners):
            listener()

    def async_set_updated_data(self, data):
        self.data = data
        self._notify_listeners()

    async def async_shutdown(self):
        return None


class CoordinatorEntity(Generic[_DataT]):
    """Minimal coordinator entity."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self.entity_id = None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_added_to_hass(self):
        return None

    def async_write_ha_state(self):
        return None


update_coordinator = _attr(
    _module("homeassistant.helpers.update_coordinator"),
    DataUpdateCoordinator=DataUpdateCoordinator,
    CoordinatorEntity=CoordinatorEntity,
    UpdateFailed=UpdateFailed,
)


class AddEntitiesCallback:
    """Stand-in for the add entities callback."""


entity_platform = _attr(_module("homeassistant.helpers.entity_platform"), AddEntitiesCallback=AddEntitiesCallback)


class Store:
    """Minimal in-memory stand-in for homeassistant.helpers.storage.Store."""

    def __init__(self, hass, version, key, **kwargs):
        self.hass = hass
        self.version = version
        self.key = key
        self.data = None
        self.saved: list = []

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data
        self.saved.append(data)

    def async_delay_save(self, data_func, delay: float = 0):
        self.data = data_func()
        self.saved.append(self.data)

    def __class_getitem__(cls, item):  # Store[dict] in annotations
        return cls


storage = _attr(_module("homeassistant.helpers.storage"), Store=Store)


# --------------------------------------------------------------------------- #
# components
# --------------------------------------------------------------------------- #
class SensorStateClass:
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


class SensorEntity:
    """Minimal sensor."""

    _attr_has_entity_name = False
    _attr_should_poll = True
    _attr_state_class = None
    _attr_native_value = None

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self):
        return None

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def name(self):
        return getattr(self, "_attr_name", None)

    @property
    def translation_key(self):
        return getattr(self, "_attr_translation_key", None)

    @property
    def device_info(self):
        return None

    @property
    def icon(self):
        return getattr(self, "_attr_icon", None)


class BinarySensorDeviceClass:
    SAFETY = "safety"
    RUNNING = "running"


class BinarySensorEntity(SensorEntity):
    """Minimal binary sensor."""

    @property
    def is_on(self):
        return False


sensor_module = _attr(_module("homeassistant.components.sensor"), SensorEntity=SensorEntity, SensorStateClass=SensorStateClass)
binary_sensor_module = _attr(
    _module("homeassistant.components.binary_sensor"),
    BinarySensorEntity=BinarySensorEntity,
    BinarySensorDeviceClass=BinarySensorDeviceClass,
)
components = _module("homeassistant.components")
components.sensor = sensor_module
components.binary_sensor = binary_sensor_module


class GeolocationEvent:
    """Minimal stand-in for homeassistant.components.geo_location.GeolocationEvent."""

    _attr_should_poll = True
    _attr_source = None
    _attr_distance = None
    _attr_latitude = None
    _attr_longitude = None
    _attr_unique_id = None

    @property
    def state(self):
        return round(self._attr_distance, 1) if self._attr_distance is not None else None

    @property
    def source(self):
        return self._attr_source

    @property
    def distance(self):
        return self._attr_distance

    @property
    def latitude(self):
        return self._attr_latitude

    @property
    def longitude(self):
        return self._attr_longitude

    @property
    def state_attributes(self):
        return {
            "source": self.source,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }

    @property
    def extra_state_attributes(self):
        return None

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def name(self):
        return getattr(self, "_attr_name", None)

    @property
    def device_info(self):
        return None

    async def async_added_to_hass(self):
        return None

    async def async_remove(self):
        self.removed = True

    def async_write_ha_state(self):
        return None


components.geo_location = _attr(
    _module("homeassistant.components.geo_location"), GeolocationEvent=GeolocationEvent
)


# --------------------------------------------------------------------------- #
# hass
# --------------------------------------------------------------------------- #
class FakeBus:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_type, event_data=None, **kwargs):
        self.events.append((event_type, event_data or {}))


class FakeConfigEntries:
    def __init__(self):
        self.entries: dict[str, ConfigEntry] = {}
        self.unique_ids: set[str] = set()
        self.reloads: list[str] = []
        self.forwarded: list[tuple[str, tuple]] = []
        self.unloaded: list[str] = []

    def async_get_known_entry(self, entry_id):
        return self.entries[entry_id]

    def async_update_entry(self, entry, **kwargs):
        for key, value in kwargs.items():
            setattr(entry, key, value)

    async def async_forward_entry_setups(self, entry, platforms):
        self.forwarded.append((entry.entry_id, tuple(platforms)))
        return True

    async def async_unload_platforms(self, entry, platforms):
        self.unloaded.append(entry.entry_id)
        return True

    async def async_reload(self, entry_id):
        self.reloads.append(entry_id)
        return True


class FakeConfig:
    """Minimal stand-in for the Home Assistant config (home coordinates)."""

    def __init__(self, latitude=48.2082, longitude=16.3738):
        self.latitude = latitude
        self.longitude = longitude


class FakeHass:
    def __init__(self, session: Session | None = None):
        self.bus = FakeBus()
        self.config_entries = FakeConfigEntries()
        self.config = FakeConfig()
        self.session = session or Session({})
        self.data: dict = {}
        self.loop = None
        self.tasks: list = []

    def async_create_task(self, target, name=None, eager_start=True):
        task = asyncio.ensure_future(target)
        self.tasks.append(task)
        return task


def add_entry(hass: FakeHass, **kwargs) -> ConfigEntry:
    entry = ConfigEntry(**kwargs)
    hass.config_entries.entries[entry.entry_id] = entry
    return entry


def run(coro):
    """Run a coroutine on a fresh event loop."""
    return asyncio.run(coro)


def install(lib_path: str | None = None) -> None:
    """Put the repository root (and optional libs) on sys.path."""
    import pathlib

    root = str(pathlib.Path(__file__).resolve().parent.parent)
    for path in (root, lib_path):
        if path and path not in sys.path:
            sys.path.insert(0, path)
    wire()


def wire() -> None:
    """Link the fake submodules to their parents.

    ``from homeassistant import config_entries`` needs the parent package to
    exist and to carry the submodule as an attribute.
    """
    root = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    for name, module in list(sys.modules.items()):
        if not name.startswith("homeassistant."):
            continue
        parent_name, _, child = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, child, module)
    return root


wire()
