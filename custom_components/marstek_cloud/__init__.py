"""Marstek Cloud Battery Home Assistant Integration.

Original work by @DoctaShizzle: https://github.com/DoctaShizzle/marstek_cloud
This fork adds HACS support, Energy Dashboard integration, and production enhancements.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import MarstekAPI, MarstekCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Marstek from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry containing integration configuration.

    Returns:
        True if setup was successful, False otherwise.
    """
    try:
        # Pre-import platforms to avoid blocking import inside event loop
        for platform in PLATFORMS:
            __import__(f"{__package__}.{platform}")

        session = async_get_clientsession(hass)
        api = MarstekAPI(session, entry.data["email"], entry.data["password"])

        scan_interval = entry.options.get(
            "scan_interval",
            entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL),
        )

        coordinator = MarstekCoordinator(hass, api, scan_interval)
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        # Ensure devices key exists in config_entry.data
        devices = coordinator.data or []
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "devices": devices}
        )

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.info("Marstek Cloud integration setup completed successfully")
        return True

    except Exception as ex:
        _LOGGER.error("Failed to setup Marstek Cloud integration: %s", ex)
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to unload.

    Returns:
        True if unload was successful, False otherwise.
    """
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok:
            hass.data[DOMAIN].pop(entry.entry_id, None)
            _LOGGER.info("Marstek Cloud integration unloaded successfully")
        return unload_ok
    except Exception as ex:
        _LOGGER.error("Failed to unload Marstek Cloud integration: %s", ex)
        return False
