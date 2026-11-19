"""Config flow: one instance, and the Send action follows the entry."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service import async_get_all_descriptions
from pytest_homeassistant.common import MockConfigEntry

from custom_components.call_webhook.const import DOMAIN, SERVICE_SEND

COMPONENT = Path("custom_components/call_webhook")


async def test_user_flow_creates_one_entry_and_registers_send(hass: HomeAssistant) -> None:
    """Adding Call Webhook creates the entry and registers Send."""
    assert not hass.services.has_service(DOMAIN, SERVICE_SEND)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Call Webhook"
    assert result["data"] == {}
    assert result["result"].unique_id == DOMAIN

    await hass.async_block_till_done()
    assert result["result"].state is ConfigEntryState.LOADED
    assert hass.services.has_service(DOMAIN, SERVICE_SEND)


async def test_second_instance_is_refused(hass: HomeAssistant) -> None:
    """The manifest allows one entry, and a second user flow aborts."""
    MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
    assert not hass.services.has_service(DOMAIN, SERVICE_SEND)


async def test_send_unregisters_when_entry_unloads(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The action exists only while the entry is loaded."""
    assert hass.services.has_service(DOMAIN, SERVICE_SEND)

    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, SERVICE_SEND)

    assert await hass.config_entries.async_setup(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service(DOMAIN, SERVICE_SEND)


async def test_send_is_described_for_the_visual_editor(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """services.yaml selectors and the translated name Send are both present."""
    descriptions = await async_get_all_descriptions(hass)
    send = descriptions[DOMAIN][SERVICE_SEND]
    assert send["response"] == {"optional": True}

    fields = send["fields"]
    assert fields["url"]["required"] is True
    assert fields["url"]["selector"]["text"]["type"] == "url"
    assert fields["bearer_token"]["selector"]["text"]["type"] == "password"
    assert "object" in fields["data"]["selector"]
    assert "sensor.myip" in fields["data"]["example"]
    assert fields["method"]["default"] == "POST"
    assert fields["method"]["selector"]["select"]["options"] == [
        "POST",
        "PUT",
        "PATCH",
        "GET",
        "DELETE",
    ]
    assert "object" in fields["headers"]["selector"]
    assert fields["timeout"]["default"] == 10
    assert fields["timeout"]["selector"]["number"]["min"] == 1
    assert fields["timeout"]["selector"]["number"]["max"] == 300
    assert fields["verify_ssl"]["default"] is True
    assert "boolean" in fields["verify_ssl"]["selector"]

    strings = json.loads((COMPONENT / "strings.json").read_text())
    english = json.loads((COMPONENT / "translations" / "en.json").read_text())
    assert english == strings
    assert strings["services"]["send"]["name"] == "Send"
    assert set(strings["services"]["send"]["fields"]) == set(fields)


def test_manifest_matches_the_approved_names() -> None:
    """Domain, display name, and version stay on the names Rob approved."""
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["domain"] == DOMAIN
    assert manifest["name"] == "Call Webhook"
    assert manifest["version"] == "0.1.0"
    assert manifest["categories"] == ["diy_makers.web_data_connectors"]
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "cloud_push"
    assert manifest["requirements"] == []
    assert manifest["single_config_entry"] is True
    assert manifest["codeowners"] == ["@rbridal"]
    assert manifest["documentation"] == "https://github.com/rbridal/ha-call-webhook"
    assert manifest["issue_tracker"] == "https://github.com/rbridal/ha-call-webhook/issues"
