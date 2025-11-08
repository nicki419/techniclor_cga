import logging

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST
from .technicolor_cga import TechnicolorCGA
from .config_flow import TechnicolorCGAOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)

DOMAIN = "technicolor_cga"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Technicolor CGA from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    router = entry.data[CONF_HOST]  # Use CONF_HOST to get the router

    _LOGGER.info("[TCGA] Setting up integration for router=%s", router)

    try:
        technicolor_cga = TechnicolorCGA(username, password, router)
        await hass.async_add_executor_job(technicolor_cga.login)
        _LOGGER.info("[TCGA] Login successful to router=%s", router)
    except Exception:
        _LOGGER.exception("[TCGA] Failed to log in to Technicolor CGA (router=%s)", router)
        return False

    hass.data[DOMAIN][entry.entry_id] = technicolor_cga
    _LOGGER.info("[TCGA] Forwarding entry setups for platforms: sensor, device_tracker")
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "device_tracker"])  # Await per HA 2025.1 requirements

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "device_tracker"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

