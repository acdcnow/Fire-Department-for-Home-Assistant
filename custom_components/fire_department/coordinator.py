"""Data update coordinator for the Fire Department Austria integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import provider
from .const import (
    DOMAIN,
    KIND_ACTIVE,
    SIGNAL_INCIDENT_CLOSED,
    SIGNAL_NEW_INCIDENT,
)

_LOGGER = logging.getLogger(__name__)

FETCH_TIMEOUT = 20
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
USER_AGENT = (
    "HomeAssistant-FireDepartment/3.0 "
    "(+https://github.com/acdcnow/fire-department-for-Home-Assistant)"
)


class FireDepartmentCoordinator(DataUpdateCoordinator[dict[str, list[dict[str, Any]]]]):
    """Fetch and parse all configured sources of one config entry.

    Sources that share a URL are downloaded only once per refresh.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        sources: list[dict[str, Any]],
        update_interval_minutes: int,
        color_scheme: str,
        categories: list[str],
        max_items: int,
    ) -> None:
        """Initialise the coordinator."""
        self.sources = sources
        self.color_scheme = color_scheme
        self.categories = categories
        self.max_items = max_items
        self.fetched_at = None
        self.last_error: str | None = None
        self.failed_sources: set[str] = set()
        self._known_ids: dict[str, dict[str, dict]] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            config_entry=entry,
            update_interval=timedelta(minutes=update_interval_minutes),
        )

    # ------------------------------------------------------------------ #
    # fetching
    # ------------------------------------------------------------------ #
    async def _async_update_data(self) -> dict[str, list[dict[str, Any]]]:
        """Download every distinct URL once and parse it per source."""
        session = async_get_clientsession(self.hass)
        documents: dict[str, str] = {}
        failed: set[str] = set()
        self.last_error = None

        for url in dict.fromkeys(source["url"] for source in self.sources):
            try:
                documents[url] = await self._download(session, url)
            except Exception as err:  # noqa: BLE001 - report, keep other sources alive
                failed.add(url)
                self.last_error = f"{url}: {type(err).__name__}: {err}"
                _LOGGER.warning("Could not read %s: %s", url, err)

        self.failed_sources = {
            source["id"] for source in self.sources if source["url"] in failed
        }

        data: dict[str, list[dict[str, Any]]] = {}
        now = dt_util.now(provider.TZ)
        for source in self.sources:
            text = documents.get(source["url"])
            if text is None:
                continue
            try:
                rows = provider.parse_source(
                    text, source, now, self.color_scheme, self.categories
                )
            except Exception as err:  # noqa: BLE001 - a broken parser must not kill the rest
                self.last_error = f"{source['url']}: {type(err).__name__}: {err}"
                _LOGGER.exception("Could not parse %s", source["url"])
                continue
            data[source["id"]] = provider.sort_rows(rows)

        if not data:
            raise UpdateFailed(
                "No source could be read. " + (self.last_error or "Check the configured URLs.")
            )

        self.fetched_at = dt_util.utcnow()
        self._notify_bus(data)
        return data

    async def _download(self, session, url: str) -> str:
        """Download one page and decode it."""
        headers = {"User-Agent": USER_AGENT, "Cache-Control": "no-cache"}
        async with asyncio.timeout(FETCH_TIMEOUT):
            async with session.get(url, headers=headers, allow_redirects=True) as response:
                if response.status != 200:
                    raise UpdateFailed(f"HTTP {response.status} for {url}")
                raw = await response.read()
        if len(raw) > MAX_RESPONSE_BYTES:
            raise UpdateFailed(f"response of {url} is unexpectedly large")
        content_type = response.headers.get("Content-Type", "")
        charset = None
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()
        return provider.decode_bytes(raw, charset)

    # ------------------------------------------------------------------ #
    # automation events
    # ------------------------------------------------------------------ #
    def _notify_bus(self, data: dict[str, list[dict[str, Any]]]) -> None:
        """Fire an event for every new / finished active mission.

        The first refresh only primes the internal cache, so a Home Assistant
        restart does not flood automations with events.
        """
        for source in self.sources:
            if source["kind"] != KIND_ACTIVE:
                continue
            rows = data.get(source["id"])
            if rows is None:
                continue
            key = source["id"]
            current = {row["id"]: row for row in rows if row.get("id")}
            previous = self._known_ids.get(key)
            self._known_ids[key] = current
            if previous is None:
                continue
            for row_id, row in current.items():
                if row_id not in previous:
                    self._fire(SIGNAL_NEW_INCIDENT, source, row)
            for row_id, row in previous.items():
                if row_id not in current:
                    self._fire(SIGNAL_INCIDENT_CLOSED, source, row)

    def _fire(self, signal: str, source: dict, row: dict) -> None:
        self.hass.bus.async_fire(
            signal,
            {
                "entry_id": self.config_entry.entry_id if self.config_entry else None,
                "source": source["id"],
                "region": source.get("region"),
                "incident": row,
            },
        )
