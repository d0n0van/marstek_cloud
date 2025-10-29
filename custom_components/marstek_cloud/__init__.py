"""Marstek Cloud Battery Home Assistant Integration.

Original work by @DoctaShizzle: https://github.com/DoctaShizzle/marstek_cloud
This fork adds HACS support, Energy Dashboard integration, and production enhancements.

Security Note:
    Passwords are accessed from config entry data (encrypted at rest by Home Assistant)
    and passed to the API client. They are never logged or exposed in any way.
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


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update for the integration.
    
    Args:
        hass: The Home Assistant instance.
        entry: The config entry that was updated.
    """
    try:
        # Get the coordinator
        coordinator = hass.data[DOMAIN].get(entry.entry_id)
        if not coordinator:
            _LOGGER.warning("No coordinator found for entry %s", entry.entry_id)
            return
            
        # Check if email or password changed - if so, reload the integration
        # since the API client needs new credentials
        if hasattr(coordinator, 'api'):
            current_email = coordinator.api._email if hasattr(coordinator.api, '_email') else None
            current_password = coordinator.api._password if hasattr(coordinator.api, '_password') else None
            
            new_email = entry.data.get("email")
            new_password = entry.data.get("password")
            
            if (current_email != new_email or current_password != new_password):
                _LOGGER.info("Credentials changed, reloading integration...")
                await hass.config_entries.async_reload(entry.entry_id)
                return
            
        # Check if scan_interval changed (check both options and data)
        new_scan_interval = entry.options.get("scan_interval") or entry.data.get("scan_interval")
        if new_scan_interval and hasattr(coordinator, 'update_scan_interval'):
            # Validate the new interval
            if 10 <= new_scan_interval <= 3600:
                coordinator.update_scan_interval(new_scan_interval)
                _LOGGER.info("Scan interval updated to %d seconds", new_scan_interval)
            else:
                _LOGGER.warning("Invalid scan interval %d, must be between 10 and 3600 seconds", 
                              new_scan_interval)
            
    except Exception as ex:
        _LOGGER.error("Failed to handle options update: %s", ex)


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
        # Security: Password from config entry (encrypted at rest by HA)
        # Never logged or exposed - passed directly to API client
        api = MarstekAPI(session, entry.data["email"], entry.data["password"])

        scan_interval = entry.options.get(
            "scan_interval",
            entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL),
        )
        
        _LOGGER.info("Setting up coordinator with scan_interval=%d from options=%s, data=%s", 
                    scan_interval, entry.options.get("scan_interval"), entry.data.get("scan_interval"))

        coordinator = MarstekCoordinator(hass, api, scan_interval)
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        # Ensure devices key exists in config_entry.data
        # Security: This preserves all config data including password (encrypted at rest)
        devices = coordinator.data or []
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "devices": devices}
        )

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        # Set up options update listener
        entry.async_on_unload(
            entry.add_update_listener(async_options_updated)
        )
        
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
            # Cleanup coordinator resources
            coordinator = hass.data[DOMAIN].get(entry.entry_id)
            if coordinator and hasattr(coordinator, 'close'):
                await coordinator.close()
            hass.data[DOMAIN].pop(entry.entry_id, None)
            _LOGGER.info("Marstek Cloud integration unloaded successfully")
        return unload_ok
    except Exception as ex:
        _LOGGER.error("Failed to unload Marstek Cloud integration: %s", ex)
        return False
