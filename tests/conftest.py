"""Shared fixtures for Call Webhook tests."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.call_webhook.const import DOMAIN


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A single Call Webhook entry with no stored options."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Call Webhook",
        data={},
        unique_id=DOMAIN,
        version=1,
    )


@pytest.fixture
async def setup_integration(hass: HomeAssistant, config_entry: MockConfigEntry) -> MockConfigEntry:
    """Load the entry so call_webhook.send is registered."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
