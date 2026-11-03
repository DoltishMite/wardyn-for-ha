"""Setting it up: Wardyn's Home Assistant link code (Wardyn → Settings → Home Assistant). Configure: Wardyn in the sidebar or not."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from . import api
from .const import CONF_CODE, CONF_PANEL, DOMAIN
from .hpcrypto import SealError, keys_for, norm, open_doc
from .core.parse import is_link

CODE = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def probe(hass: HomeAssistant, raw: str) -> tuple[str | None, str]:
    """(normalised code, its copy's id prefix for unique_id) for a working link code, or (None, error key)."""
    code = norm(raw)
    if len(code) < 16:
        return None, "invalid_code"
    keys = keys_for(code)
    try:
        v, doc = await api.get_doc(async_get_clientsession(hass), keys)
        if not v:
            return None, "not_found"
        obj = await hass.async_add_executor_job(open_doc, doc, keys)
    except api.Refused:
        return None, "refused"
    except api.ApiError:
        return None, "cannot_connect"
    except SealError:
        return None, "invalid_code"
    if not is_link(obj):
        return None, "not_a_link"
    return code, keys.id[:16]


class WardynConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code, res = await probe(self.hass, user_input[CONF_CODE])
            if code is None:
                errors[CONF_CODE if res in ("invalid_code", "not_found", "not_a_link") else "base"] = res
            else:
                await self.async_set_unique_id(res)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Wardyn", data={CONF_CODE: code}, options={CONF_PANEL: user_input.get(CONF_PANEL, True)})
        schema = vol.Schema({vol.Required(CONF_CODE): CODE, vol.Optional(CONF_PANEL, default=True): bool})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A new link code (Wardyn's ↻ New code): the entities stay."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code, res = await probe(self.hass, user_input[CONF_CODE])
            if code is None:
                errors[CONF_CODE if res in ("invalid_code", "not_found", "not_a_link") else "base"] = res
            else:
                return self.async_update_reload_and_abort(self._get_reconfigure_entry(), unique_id=res, data={CONF_CODE: code})
        return self.async_show_form(step_id="reconfigure", data_schema=vol.Schema({vol.Required(CONF_CODE): CODE}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> WardynOptionsFlow:
        return WardynOptionsFlow()


class WardynOptionsFlow(OptionsFlow):   # (no reload: __init__._options_changed adds or removes the panel)
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={CONF_PANEL: user_input[CONF_PANEL]})
        schema = vol.Schema({vol.Required(CONF_PANEL, default=self.config_entry.options.get(CONF_PANEL, True)): bool})
        return self.async_show_form(step_id="init", data_schema=schema)
