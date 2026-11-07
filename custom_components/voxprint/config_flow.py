"""Set up Voxprint: the app's URL, the satellites to listen to, and the speakers as subentries."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME, CONF_URL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector as sel
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.hassio import is_hassio
import probatio as vol

from .client import AppClient, AppError
from .const import (
    APP_PORT,
    APP_SLUG,
    CONF_PERSON,
    CONF_SATELLITES,
    CONF_THRESHOLD,
    DEFAULT_THRESHOLD,
    DOMAIN,
    SUBENTRY_SPEAKER,
)

SATELLITES = sel.EntitySelector(sel.EntitySelectorConfig(domain=Platform.ASSIST_SATELLITE, multiple=True))
URL_SCHEMA = vol.Schema(
    {vol.Required(CONF_URL): sel.TextSelector(sel.TextSelectorConfig(type=sel.TextSelectorType.URL))}
)
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SATELLITES): SATELLITES,
        vol.Required(CONF_THRESHOLD): sel.NumberSelector(
            sel.NumberSelectorConfig(min=0.1, max=0.95, step=0.01, mode=sel.NumberSelectorMode.BOX)
        ),
    }
)
SPEAKER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): sel.TextSelector(),
        vol.Optional(CONF_PERSON): sel.EntitySelector(sel.EntitySelectorConfig(domain="person")),
    }
)


@callback
def _default_url(hass: HomeAssistant) -> str:
    """The installed app's address on Home Assistant OS, or a host port elsewhere."""
    if is_hassio(hass):
        # Imported here: the hassio integration's requirements exist only where the Supervisor runs.
        from homeassistant.components.hassio import HassioNotReadyError, get_apps_list, hostname_from_addon_slug

        try:
            apps = get_apps_list(hass)
        except HassioNotReadyError:
            apps = []
        for app in apps:
            slug = str(app.get("slug", ""))
            # A repository app's slug is "<repository hash>_voxprint", a local one's "local_voxprint".
            if slug.rpartition("_")[2] == APP_SLUG:
                return f"http://{hostname_from_addon_slug(slug)}:{APP_PORT}"
    return f"http://localhost:{APP_PORT}"


async def _async_check_app(hass: HomeAssistant, url: str) -> str | None:
    """The error key for an app that can't be used, or None."""
    try:
        await AppClient(async_get_clientsession(hass), url).health()
    except AppError as err:
        return "app_incompatible" if err.code == "app_incompatible" else "cannot_connect"
    return None


def _satellite_errors(user_input: dict[str, Any]) -> dict[str, str]:
    return {} if user_input[CONF_SATELLITES] else {CONF_SATELLITES: "no_satellite_selected"}


class VoxprintConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_SPEAKER: SpeakerSubentryFlow}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return VoxprintOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        satellites = self.hass.states.async_entity_ids(Platform.ASSIST_SATELLITE)
        if not satellites:
            return self.async_abort(reason="no_satellites")
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            errors = _satellite_errors(user_input)
            if not errors:
                error = await _async_check_app(self.hass, url)
                errors = {"base": error} if error else {}
            if not errors:
                return self.async_create_entry(
                    title="Voxprint",
                    data={CONF_URL: url},
                    options={CONF_SATELLITES: user_input[CONF_SATELLITES], CONF_THRESHOLD: DEFAULT_THRESHOLD},
                )
        schema = URL_SCHEMA.extend({vol.Required(CONF_SATELLITES): SATELLITES})
        suggested = user_input or {CONF_URL: _default_url(self.hass), CONF_SATELLITES: satellites}
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, suggested), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            error = await _async_check_app(self.hass, url)
            if error is None:
                return self.async_update_and_abort(entry, data_updates={CONF_URL: url})
            errors = {"base": error}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(URL_SCHEMA, user_input or dict(entry.data)),
            errors=errors,
        )


class VoxprintOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and not (errors := _satellite_errors(user_input)):
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, user_input or dict(self.config_entry.options)
            ),
            errors=errors,
        )


class SpeakerSubentryFlow(ConfigSubentryFlow):
    """A speaker: a name, and optionally the person it is."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name, data = _speaker(user_input)
            if not (errors := self._name_errors(name, None)):
                return self.async_create_entry(title=name, data=data)
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(SPEAKER_SCHEMA, user_input), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            name, data = _speaker(user_input)
            if not (errors := self._name_errors(name, subentry.subentry_id)):
                return self.async_update_and_abort(self._get_entry(), subentry, title=name, data=data)
        suggested = user_input or {CONF_NAME: subentry.title, **subentry.data}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(SPEAKER_SCHEMA, suggested),
            errors=errors,
        )

    def _name_errors(self, name: str, own_id: str | None) -> dict[str, str]:
        if not name:
            return {CONF_NAME: "name_empty"}
        taken = {
            subentry.title.casefold()
            for subentry in self._get_entry().get_subentries_of_type(SUBENTRY_SPEAKER)
            if subentry.subentry_id != own_id
        }
        return {CONF_NAME: "name_taken"} if name.casefold() in taken else {}


def _speaker(user_input: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    name = user_input[CONF_NAME].strip()
    person = user_input.get(CONF_PERSON)
    return name, {CONF_PERSON: person} if person else {}
