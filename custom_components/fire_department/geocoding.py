"""Resolve the municipality of a mission to coordinates.

None of the Austrian mission lists publishes coordinates, so the town name has
to be translated into a position before it can be shown on the built-in map
(see :mod:`geo_location`).

Lookups are cached permanently - negative results included - and throttled to
one request per second, which is what the Nominatim usage policy asks for:
https://operations.osmfoundation.org/policies/nominatim/

The map markers (and with them every lookup) can be switched off in the
options, so an installation that does not want this external request never
makes one.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import (
    GEOCODE_BLOCK_TIME,
    GEOCODE_COUNTRY,
    GEOCODE_MIN_INTERVAL,
    GEOCODE_STORAGE_KEY,
    GEOCODE_STORAGE_VERSION,
    GEOCODE_TIMEOUT,
    GEOCODE_URL,
    GEOCODE_USER_AGENT,
    REGION_STATES,
)

_LOGGER = logging.getLogger(__name__)

#: written at most every two minutes, the cache lives in memory as well
SAVE_DELAY = 120

_PREFIX_RE = re.compile(r"^\s*(stadt|markt|marktgemeinde|gemeinde)\s+", re.IGNORECASE)
_SUFFIX_RE = re.compile(r"[\s-]+(stadt|markt)\s*$", re.IGNORECASE)
#: ``ss`` / ``SS`` - the sources fold the German sharp s whenever they feel like it
_SS_RE = re.compile(r"s{2}", re.IGNORECASE)
_CONNECTIVES = {
    "an", "am", "auf", "bei", "der", "die", "im", "in",
    "ob", "unter", "von", "vor", "zu", "zur", "zum",
}


def _is_shouting(text: str) -> bool:
    """True for names published in capitals.

    ``str.isupper()`` is not enough here: the letter ``ß`` counts as lower case,
    so a name like ``WEISSENKIRCHEN`` would slip through in its ``ß`` spelling.
    """
    return not any(char.islower() and char not in "ß" for char in text)


def candidates(municipality: str) -> list[str]:
    """Return plausible spellings for a municipality name.

    The sources write town names in very different shapes (``Grossdietmanns``,
    ``Stadt Gmünd``, ``GöPFRITZ AN DER WILD``, ``Zwettl-Stadt``), so a couple of
    variants are tried before a lookup is stored as "not found".
    """
    base = municipality.strip()
    if not base:
        return []

    cleaned = _SUFFIX_RE.sub("", _PREFIX_RE.sub("", base)).strip()

    variants = [cleaned]
    if cleaned != base:
        variants.append(base)
    if _SS_RE.search(cleaned):
        # WASTL writes "Grossdietmanns", OpenStreetMap knows "Großdietmanns".
        variants.append(_SS_RE.sub("ß", cleaned))

    result: list[str] = []
    for variant in variants:
        if _is_shouting(variant):
            variant = " ".join(
                word.lower() if index and word.lower() in _CONNECTIVES else word.capitalize()
                for index, word in enumerate(variant.split())
            )
        if variant and variant not in result:
            result.append(variant)
    return result


def query_parameters(municipality: str, region: str | None = None) -> dict[str, str]:
    """Nominatim query parameters for one municipality of a federal state."""
    state = REGION_STATES.get(region or "")
    query = ", ".join(part for part in (municipality, state, GEOCODE_COUNTRY) if part)
    return {
        "q": query,
        "format": "jsonv2",
        "limit": "1",
        "countrycodes": "at",
        "addressdetails": "0",
    }


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

    @property
    def cache(self) -> dict[str, list[float] | None]:
        """Known lookups, including the ones that were not found."""
        return self._cache

    async def async_load(self) -> None:
        """Load the persistent cache once."""
        if self._loaded:
            return
        self._loaded = True
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._cache = stored

    async def async_lookup(
        self, municipality: str | None, region: str | None = None
    ) -> tuple[float, float] | None:
        """Return ``(latitude, longitude)`` for a municipality, if it is known."""
        if not municipality or municipality == "-":
            return None

        key = f"{region or 'at'}|{municipality.strip().casefold()}"
        await self.async_load()

        if key in self._cache:
            cached = self._cache[key]
            return (cached[0], cached[1]) if cached else None

        coords = await self._async_geocode(municipality, region)
        self._cache[key] = [coords[0], coords[1]] if coords else None
        self._store.async_delay_save(lambda: self._cache, SAVE_DELAY)
        return coords

    async def _throttle(self) -> None:
        """Keep the request rate below one per second."""
        wait = GEOCODE_MIN_INTERVAL - (time.monotonic() - self._last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    async def _async_geocode(
        self, municipality: str, region: str | None
    ) -> tuple[float, float] | None:
        """Ask Nominatim for every plausible spelling of the name."""
        async with self._lock:
            session = async_get_clientsession(self._hass)
            for candidate in candidates(municipality):
                if time.monotonic() < self._blocked_until:
                    return None

                await self._throttle()
                try:
                    async with asyncio.timeout(GEOCODE_TIMEOUT):
                        async with session.get(
                            GEOCODE_URL,
                            params=query_parameters(candidate, region),
                            headers={"User-Agent": GEOCODE_USER_AGENT},
                        ) as response:
                            status = response.status
                            payload = (
                                await response.json(content_type=None) if status == 200 else None
                            )
                except Exception as err:  # noqa: BLE001 - one failed lookup is not fatal
                    _LOGGER.debug("Geocoding %s failed: %s", candidate, err)
                    continue

                if status in (403, 429):
                    _LOGGER.warning(
                        "Nominatim refused the lookup (%s); pausing geocoding for %s seconds",
                        status,
                        GEOCODE_BLOCK_TIME,
                    )
                    self._blocked_until = time.monotonic() + GEOCODE_BLOCK_TIME
                    return None
                if status != 200:
                    _LOGGER.debug("Unexpected geocoding status %s for %s", status, candidate)
                    continue
                if not isinstance(payload, list) or not payload:
                    continue
                try:
                    return (float(payload[0]["lat"]), float(payload[0]["lon"]))
                except (KeyError, TypeError, ValueError):
                    continue

            _LOGGER.debug("No coordinates found for %s", municipality)
            return None
