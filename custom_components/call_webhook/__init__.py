"""The Call Webhook integration.

The Send action is registered when the config entry loads and removed when
the entry unloads. New webhook URLs are fields on the action, so they do not
need a YAML edit or a reload.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, SupportsResponse

from .const import DOMAIN, SERVICE_SEND
from .webhook import SEND_SCHEMA, async_handle_send

type CallWebhookConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: CallWebhookConfigEntry) -> bool:
    """Register call_webhook.send for a loaded entry."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND,
        async_handle_send,
        schema=SEND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CallWebhookConfigEntry) -> bool:
    """Remove call_webhook.send when the entry unloads."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND):
        hass.services.async_remove(DOMAIN, SERVICE_SEND)
    return True
