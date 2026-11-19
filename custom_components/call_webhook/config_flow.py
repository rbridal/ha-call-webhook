"""Config flow for Call Webhook.

One instance. Webhook URLs and tokens live on each action, so adding another
webhook does not need a new entry or a reload.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
import probatio

from .const import DOMAIN, INTEGRATION_NAME


class CallWebhookConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a single Call Webhook config entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding the integration."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=probatio.Schema({}),
            )

        return self.async_create_entry(title=INTEGRATION_NAME, data={})
