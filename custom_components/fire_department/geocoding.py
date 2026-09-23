"""Resolve the municipality of an operation to coordinates.

The WASTL pages do not publish any coordinates, so the municipality name has to
be translated into a position before it can be shown on the built-in Home
Assistant map (``geo_location`` platform).

The lookups are cached persistently (also negative results) and throttled to at
most one request per second, which is what the Nominatim usage policy asks for:
https://operations.osmfoundation.org/policies/nominatim/

Set ``GEOCODE_ENABLED`` in ``const.py`` to ``False`` for a fully offline
installation - the dashboard then simply shows no map markers.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import (
    GEOCODE_ENABLED,
    GEOCODE_MIN_INTERVAL,
    GEOCODE_REGION,
    GEOCODE_STORAGE_KEY,
    GEOCODE_STORAGE_VERSION,
    GEOCODE_URL,
    GEOCODE_USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10
BLOCK_TIME = 600  # seconds to back off after 403/429
STORAGE_SAVE_DELAY = 120

_PREFIX_RE = re.compile(r"^\s*(stadt|markt|marktgemeinde|gemeinde)\s+", re.IGNORECASE)
_SUFFIX_RE = re.compile(r"[\s-]+(stadt|markt)\s*$", re.IGNORECASE)
_CONNECTIVES = {
    "an", "am", "auf", "bei", "der", "die", "im", "in",
    "ob", "unter", "von", "vor", "zu", "zur", "zum",
}


def candidates(name: str) -> list[str]:
    """Return plausible spellings for a municipality from the WASTL tables.

    The source writes names in many shapes ("Grossdietmanns", "Stadt Gmünd",
    "GöPFRITZ AN DER WILD", "Zwettl-Stadt"), so a couple of variants are tried
    before a lookup is stored as "not found".
    """
    base = name.strip()
    if not base:
        return []

    cleaned = _SUFFIX_RE.sub("", _PREFIX_RE.sub("", base)).strip()

    variants = [cleaned]
    if cleaned != base:
        variants.append(base)
    if "ss" in cleaned:
        # WASTL points out "Grossdietmanns", OSM knows "Großdietmanns".
        variants.append(cleaned.replace("ss", "ß"))

    result: list[str] = []
    for variant in variants:
        if variant.isupper():
            variant = " ".join(
                word.lower() if idx and word.lower() in _CONNECTIVES else word.capitalize()
                for idx, word in enumerate(variant.split())
            )
        if variant and variant not in result:
            result.append(variant)
    return result


class MunicipalityGeocoder:
    """Cached and throttled municipality lookup."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the geocoder."""
        self._hass = hass
        self._store: Store[dict[str, list[float] | None]] = Store(
            hass, GEOCODE_STORAGE_VERSION, GEOCODE_STORAGE_KEY
        )
        self._cache: dict[str, list[float] | None] = {}
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._blocked_until = 0.0
        self._loaded = False

    async def async_load(self) -> None:
        """Load the persistent cache once."""
        if self._loaded:
            return
        self._loaded = True
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._cache = stored

    async def async_lookup(self, municipality: str) -> tuple[float, float] | None:
        """Return (latitude, longitude) for a municipality, if it is known."""
        if not GEOCODE_ENABLED or not municipality or municipality == "-":
            return None

        key = municipality.strip().casefold()
        await self.async_load()

        if key in self._cache:
            cached = self._cache[key]
            return (cached[0], cached[1]) if cached else None

        coords = await self._async_geocode(municipality)
        self._cache[key] = [coords[0], coords[1]] if coords else None
        self._store.async_delay_save(lambda: self._cache, STORAGE_SAVE_DELAY)
        return coords

    async def _throttle(self) -> None:
        """Keep the request rate below one per second."""
        wait = GEOCODE_MIN_INTERVAL - (time.monotonic() - self._last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    async def _async_geocode(self, municipality: str) -> tuple[float, float] | None:
        """Query Nominatim for every plausible spelling of the name."""
        async with self._lock:
            session = async_get_clientsession(self._hass)
            for candidate in candidates(municipality):
                if time.monotonic() < self._blocked_until:
                    return None

                await self._throttle()
                try:
                    async with asyncio.timeout(REQUEST_TIMEOUT):
                        response = await session.get(
                            GEOCODE_URL,
                            params={
                                "q": f"{candidate}, {GEOCODE_REGION}",
                                "format": "jsonv2",
                                "limit": 1,
                                "countrycodes": "at",
                                "addressdetails": 0,
                            },
                            headers={"User-Agent": GEOCODE_USER_AGENT},
                        )
                        if response.status in (403, 429):
                            _LOGGER.warning(
                                "Nominatim refused the lookup (%s); pausing geocoding "
                                "for %s seconds",
                                response.status,
                                BLOCK_TIME,
                            )
                            self._blocked_until = time.monotonic() + BLOCK_TIME
                            return None
                        if response.status != 200:
                            _LOGGER.debug(
                                "Unexpected geocoding status %s for %s",
                                response.status,
                                candidate,
                            )
                            continue
                        payload = await response.json(content_type=None)
                except (TimeoutError, aiohttp.ClientError) as err:
                    _LOGGER.debug("Geocoding %s failed: %s", candidate, err)
                    continue

                if not isinstance(payload, list) or not payload:
                    continue

                try:
                    return (float(payload[0]["lat"]), float(payload[0]["lon"]))
                except (KeyError, TypeError, ValueError):
                    continue

            _LOGGER.debug("No coordinates found for %s", municipality)
            return None
