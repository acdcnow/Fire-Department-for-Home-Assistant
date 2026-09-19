"""Config and options flow for the Fire Department Austria integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CATEGORY_LABELS,
    COLOR_SCHEMES,
    CONF_COLOR_SCHEME,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    CONF_FILTER_CATEGORIES,
    CONF_MAX_ITEMS,
    CONF_NAME,
    CONF_PAGE_FILTER,
    CONF_PAGE_KIND,
    CONF_PAGE_NAME,
    CONF_PAGE_PARSER,
    CONF_PAGE_SELECTION,
    CONF_PAGE_URL,
    CONF_PAGE_WINDOW,
    CONF_PAGES,
    CONF_REGION,
    CONF_SOURCES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_COLOR_SCHEME,
    DEFAULT_MAX_ITEMS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    KINDS,
    MAX_MAX_ITEMS,
    MAX_UPDATE_INTERVAL,
    MIN_MAX_ITEMS,
    MIN_UPDATE_INTERVAL,
    NONE,
    PARSER_WASTL_INCIDENTS,
    PARSERS,
    REGION_LABELS,
    SOURCES,
    SUPPORTED_REGIONS,
    WINDOWS,
    region_sources,
)

_LOGGER = logging.getLogger(__name__)

#: keys used in the form -> the label the selectors show
CATEGORY_OPTIONS = list(CATEGORY_LABELS)


def _colours() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(COLOR_SCHEMES),
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="color_scheme",
        )
    )


def _categories() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=CATEGORY_OPTIONS,
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
            translation_key="category",
        )
    )


def _interval() -> vol.All:
    return vol.All(
        vol.Coerce(int), vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL)
    )


def _source_options(kind: str) -> list[str]:
    return [NONE] + [source_id for source_id, source in SOURCES.items() if source["kind"] == kind]


def _source_selector(kind: str) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=_source_options(kind),
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="source",
        )
    )


class FireDepartmentConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Pick region, colour scheme and update interval."""
        if user_input is not None:
            region = user_input[CONF_REGION]
            await self.async_set_unique_id(region)
            self._abort_if_unique_id_configured()
            sources = {
                kind: source["id"] for kind, source in region_sources(region).items()
            }
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={},
                options={
                    CONF_REGION: region,
                    CONF_SOURCES: sources,
                    CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                    CONF_COLOR_SCHEME: user_input[CONF_COLOR_SCHEME],
                    CONF_FILTER_CATEGORIES: user_input.get(CONF_FILTER_CATEGORIES) or [],
                    CONF_MAX_ITEMS: DEFAULT_MAX_ITEMS,
                    CONF_PAGES: [],
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="Fire Department"): str,
                    vol.Required(CONF_REGION, default=SUPPORTED_REGIONS[0]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(SUPPORTED_REGIONS),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="region",
                        )
                    ),
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): _interval(),
                    vol.Required(CONF_COLOR_SCHEME, default=DEFAULT_COLOR_SCHEME): _colours(),
                    vol.Optional(CONF_FILTER_CATEGORIES, default=[]): _categories(),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return FireDepartmentOptionsFlow()


class FireDepartmentOptionsFlow(OptionsFlow):
    """Changing the settings reloads the config entry automatically."""

    def __init__(self) -> None:
        """Set up empty state, filled in :meth:`async_step_init`."""
        self._options: dict = {}
        self._sources: dict[str, str] = {}
        self._pages: list[dict] = []

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """Show the options menu."""
        self._options = dict(self.config_entry.options)
        self._sources = dict(self._options.get(CONF_SOURCES) or {})
        self._pages = [dict(page) for page in self._options.get(CONF_PAGES) or []]
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "sources", "add_page", "remove_page"],
        )

    # ------------------------------------------------------------------ #
    # general settings
    # ------------------------------------------------------------------ #
    async def async_step_general(self, user_input=None) -> ConfigFlowResult:
        """Update interval, colour scheme, category filter and row limit."""
        if user_input is not None:
            self._options[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL]
            self._options[CONF_COLOR_SCHEME] = user_input[CONF_COLOR_SCHEME]
            self._options[CONF_FILTER_CATEGORIES] = user_input.get(CONF_FILTER_CATEGORIES) or []
            self._options[CONF_MAX_ITEMS] = user_input[CONF_MAX_ITEMS]
            return self._save()

        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=self._options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    ): _interval(),
                    vol.Required(
                        CONF_COLOR_SCHEME,
                        default=self._options.get(CONF_COLOR_SCHEME, DEFAULT_COLOR_SCHEME),
                    ): _colours(),
                    vol.Optional(
                        CONF_FILTER_CATEGORIES,
                        default=self._options.get(CONF_FILTER_CATEGORIES) or [],
                    ): _categories(),
                    vol.Required(
                        CONF_MAX_ITEMS,
                        default=self._options.get(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_MAX_ITEMS, max=MAX_MAX_ITEMS)),
                }
            ),
        )

    # ------------------------------------------------------------------ #
    # data sources
    # ------------------------------------------------------------------ #
    async def async_step_sources(self, user_input=None) -> ConfigFlowResult:
        """Choose which source feeds which sensor."""
        if user_input is not None:
            for kind in KINDS:
                value = user_input.get(kind, NONE)
                if value == NONE:
                    self._sources.pop(kind, None)
                else:
                    self._sources[kind] = value
            self._options[CONF_SOURCES] = self._sources
            return self._save()

        schema: dict = {}
        for kind in KINDS:
            current = self._sources.get(kind, NONE)
            if current not in _source_options(kind):
                current = NONE
            schema[vol.Optional(kind, default=current)] = _source_selector(kind)
        return self.async_show_form(step_id="sources", data_schema=vol.Schema(schema))

    # ------------------------------------------------------------------ #
    # custom sources
    # ------------------------------------------------------------------ #
    async def async_step_add_page(self, user_input=None) -> ConfigFlowResult:
        """Add a user defined source."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = (user_input.get(CONF_PAGE_URL) or "").strip()
            if not url.startswith(("http://", "https://")):
                errors[CONF_PAGE_URL] = "invalid_url"
            parser = user_input.get(CONF_PAGE_PARSER, PARSER_WASTL_INCIDENTS)
            if parser not in PARSERS:
                errors[CONF_PAGE_PARSER] = "invalid_parser"
            if not errors:
                page = {
                    CONF_PAGE_NAME: user_input.get(CONF_PAGE_NAME) or None,
                    CONF_PAGE_URL: url,
                    CONF_PAGE_PARSER: parser,
                    CONF_PAGE_KIND: user_input.get(CONF_PAGE_KIND) or KINDS[0],
                    CONF_PAGE_WINDOW: user_input.get(CONF_PAGE_WINDOW) or "custom",
                }
                page_filter = user_input.get(CONF_PAGE_FILTER, NONE)
                if page_filter != NONE:
                    page[CONF_PAGE_FILTER] = page_filter
                self._pages.append(page)
                self._options[CONF_PAGES] = self._pages
                return self._save()

        return self.async_show_form(
            step_id="add_page",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PAGE_NAME): str,
                    vol.Required(CONF_PAGE_URL): str,
                    vol.Required(CONF_PAGE_PARSER, default=PARSER_WASTL_INCIDENTS): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(PARSERS),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="parser",
                        )
                    ),
                    vol.Required(CONF_PAGE_KIND, default=KINDS[0]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(KINDS),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="kind",
                        )
                    ),
                    vol.Required(CONF_PAGE_WINDOW, default="custom"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(WINDOWS),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="window",
                        )
                    ),
                    vol.Optional(CONF_PAGE_FILTER, default=NONE): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[NONE, "ongoing", "closed"],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="row_filter",
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_remove_page(self, user_input=None) -> ConfigFlowResult:
        """Remove user defined sources again."""
        if user_input is not None:
            removed = {int(index) for index in user_input.get(CONF_PAGE_SELECTION, [])}
            self._pages = [
                page for index, page in enumerate(self._pages) if index not in removed
            ]
            self._options[CONF_PAGES] = self._pages
            return self._save()

        if not self._pages:
            return self.async_abort(reason="no_pages")

        options = [
            {
                "value": str(index),
                "label": page.get(CONF_PAGE_NAME) or page.get(CONF_PAGE_URL, f"Source {index + 1}"),
            }
            for index, page in enumerate(self._pages)
        ]
        return self.async_show_form(
            step_id="remove_page",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PAGE_SELECTION): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    # ------------------------------------------------------------------ #
    def _save(self) -> ConfigFlowResult:
        """Store the options - the config entry is reloaded afterwards."""
        self._options[CONF_SOURCES] = self._sources
        self._options[CONF_PAGES] = self._pages
        return self.async_create_entry(title="", data=self._options)


def region_title(region: str) -> str:
    """Human readable region name (used by the docs and tests)."""
    return REGION_LABELS.get(region, region)
