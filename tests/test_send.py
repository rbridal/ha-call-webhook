"""call_webhook.send: JSON body, templates, response data, errors, redaction."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp
from homeassistant.const import CONTENT_TYPE_JSON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.service import async_call_from_config
import probatio
import pytest
from pytest_homeassistant.common import MockConfigEntry
from yarl import URL

from custom_components.call_webhook.const import DOMAIN, SERVICE_SEND
from custom_components.call_webhook.webhook import redact_secrets

TOKEN = "super-secret-token"
URL_HOOK = "https://hooks.example.com/ingest"


def _call(aioclient_mock) -> tuple[str, URL, Any, dict[str, str]]:
    """Return the single recorded request."""
    assert len(aioclient_mock.mock_calls) == 1
    method, url, body, headers = aioclient_mock.mock_calls[0]
    return method, url, body, dict(headers or {})


async def test_post_json_body_and_bearer_header(
    hass: HomeAssistant, setup_integration: MockConfigEntry, aioclient_mock
) -> None:
    """POST sends a JSON body and Authorization: Bearer when a token is set."""
    aioclient_mock.post(URL_HOOK, json={"accepted": True})

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {
            "url": URL_HOOK,
            "bearer_token": TOKEN,
            "data": {"location": "shop", "n": 2},
            "headers": {"X-Source": "home-assistant", "Authorization": "Bearer other-token"},
        },
        blocking=True,
    )

    method, url, body, headers = _call(aioclient_mock)
    assert method == "POST"
    assert str(url) == URL_HOOK
    assert body == {"location": "shop", "n": 2}
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["Content-Type"] == CONTENT_TYPE_JSON
    assert headers["X-Source"] == "home-assistant"
    assert "other-token" not in headers["Authorization"]


async def test_templated_data_is_json(
    hass: HomeAssistant, setup_integration: MockConfigEntry, aioclient_mock
) -> None:
    """Automation templates render before the action, then the dict is JSON."""
    hass.states.async_set("sensor.myip", "203.0.113.10")
    aioclient_mock.post(URL_HOOK, text="ok")

    await async_call_from_config(
        hass,
        {
            "action": "call_webhook.send",
            "data": {
                "url": URL_HOOK,
                "bearer_token": TOKEN,
                "data": {
                    "ip": "{{ states('sensor.myip') }}",
                    "location": "shop",
                },
            },
        },
        blocking=True,
    )

    _method, _url, body, headers = _call(aioclient_mock)
    assert body == {"ip": "203.0.113.10", "location": "shop"}
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["Content-Type"] == CONTENT_TYPE_JSON


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
async def test_other_methods_send_json(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    aioclient_mock,
    method: str,
) -> None:
    """PUT, PATCH, and DELETE use the same JSON body as POST."""
    aioclient_mock.request(method, URL_HOOK, text="ok")
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {"url": URL_HOOK, "method": method.lower(), "data": {"location": "shop"}},
        blocking=True,
    )
    sent_method, _url, body, headers = _call(aioclient_mock)
    assert sent_method == method
    assert body == {"location": "shop"}
    assert headers["Content-Type"] == CONTENT_TYPE_JSON


async def test_get_sends_data_as_query_params(
    hass: HomeAssistant, setup_integration: MockConfigEntry, aioclient_mock
) -> None:
    """GET puts data on the query string and does not send a body."""
    aioclient_mock.get(URL_HOOK, text="ok", headers={"Content-Type": "text/plain"})
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {
            "url": URL_HOOK,
            "method": "GET",
            "data": {
                "location": "shop",
                "n": 2,
                "flag": True,
                "skip": None,
                "meta": {"a": 1},
            },
            "headers": {"Content-Type": "text/plain", "X-Source": "home-assistant"},
        },
        blocking=True,
    )
    method, url, body, headers = _call(aioclient_mock)
    assert method == "GET"
    assert body is None
    assert url.query["location"] == "shop"
    assert url.query["n"] == "2"
    assert url.query["flag"] == "true"
    assert "skip" not in url.query
    assert json.loads(url.query["meta"]) == {"a": 1}
    assert headers["Content-Type"] == "text/plain"
    assert headers["X-Source"] == "home-assistant"
    assert not any(key.lower() == "authorization" for key in headers)


async def test_response_data_json_and_text(
    hass: HomeAssistant, setup_integration: MockConfigEntry, aioclient_mock
) -> None:
    """return_response includes status, ok, headers, and a parsed body."""
    aioclient_mock.post(
        URL_HOOK,
        status=201,
        json={"accepted": True},
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "abc",
            "Connection": "close",
            "Authorization": f"Bearer {TOKEN}",
        },
    )
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {"url": URL_HOOK, "data": {"location": "shop"}},
        blocking=True,
        return_response=True,
    )
    assert response == {
        "status": 201,
        "ok": True,
        "headers": {
            "Content-Type": "application/json",
            "X-Request-Id": "abc",
            "Authorization": "***",
        },
        "body": {"accepted": True},
    }

    aioclient_mock.clear_requests()
    aioclient_mock.post(URL_HOOK, status=200, text="pong", headers={"Content-Type": "text/plain"})
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {"url": URL_HOOK},
        blocking=True,
        return_response=True,
    )
    assert response["status"] == 200
    assert response["ok"] is True
    assert response["body"] == "pong"


async def test_non_2xx_raises_unless_response_requested(
    hass: HomeAssistant, setup_integration: MockConfigEntry, aioclient_mock
) -> None:
    """HTTP errors fail the action, and response_variable callers get the body."""
    aioclient_mock.post(URL_HOOK, status=503, text="nope")
    with pytest.raises(HomeAssistantError, match="HTTP 503"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {"url": URL_HOOK, "bearer_token": TOKEN},
            blocking=True,
        )

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        URL_HOOK,
        status=422,
        json={"error": "missing location"},
        headers={"Content-Type": "application/json"},
    )
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {"url": URL_HOOK},
        blocking=True,
        return_response=True,
    )
    assert response["status"] == 422
    assert response["ok"] is False
    assert response["body"] == {"error": "missing location"}


async def test_timeout_and_client_error_raise(
    hass: HomeAssistant, setup_integration: MockConfigEntry, aioclient_mock
) -> None:
    """Timeouts and connection errors raise even when a response was requested."""
    aioclient_mock.post(URL_HOOK, exc=TimeoutError())
    with pytest.raises(HomeAssistantError, match="Timed out calling POST") as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {"url": URL_HOOK, "bearer_token": TOKEN, "timeout": 2},
            blocking=True,
            return_response=True,
        )
    assert TOKEN not in str(err.value)
    assert err.value.__cause__ is None

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        URL_HOOK,
        exc=aiohttp.ClientError(f"connection failed Authorization: Bearer {TOKEN}"),
    )
    with pytest.raises(HomeAssistantError, match="Could not call POST") as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {"url": URL_HOOK, "bearer_token": TOKEN},
            blocking=True,
            return_response=True,
        )
    message = str(err.value)
    assert TOKEN not in message
    assert "Bearer ***" in message
    assert err.value.__cause__ is None


async def test_token_is_redacted_in_debug_logs(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    aioclient_mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Debug logs show the call and hide the bearer token and Authorization value."""
    caplog.set_level(logging.DEBUG)
    aioclient_mock.post(URL_HOOK, text="ok")
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {
            "url": f"{URL_HOOK}?trace={TOKEN}",
            "bearer_token": TOKEN,
            "data": {"location": "shop"},
        },
        blocking=True,
    )

    logged = caplog.text
    assert TOKEN not in logged
    assert "Authorization" in logged
    assert "***" in logged
    method, url, _body, headers = _call(aioclient_mock)
    assert method == "POST"
    assert TOKEN in str(url)
    assert headers["Authorization"] == f"Bearer {TOKEN}"


async def test_verify_ssl_selects_the_shared_session(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    aioclient_mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """verify_ssl false uses Home Assistant's no-verify shared session."""
    seen: list[bool] = []
    original = aiohttp_client.async_get_clientsession

    def spy(hass_arg, verify_ssl=True, **kwargs):
        seen.append(verify_ssl)
        return original(hass_arg, verify_ssl=verify_ssl, **kwargs)

    monkeypatch.setattr(
        "custom_components.call_webhook.webhook.async_get_clientsession", spy
    )
    aioclient_mock.post(URL_HOOK, text="ok")
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {"url": URL_HOOK, "verify_ssl": False},
        blocking=True,
    )
    assert seen == [False]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"url": "not a url"},
        {"url": "ftp://files.example.com/hook"},
        {"url": URL_HOOK, "method": "HEAD"},
        {"url": URL_HOOK, "timeout": 0},
        {"url": URL_HOOK, "data": ["not", "an", "object"]},
        {"url": URL_HOOK, "headers": {"X-Bad": {"nested": True}}},
    ],
)
async def test_invalid_fields_are_rejected(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    aioclient_mock,
    payload: dict[str, Any],
) -> None:
    """The action schema rejects missing, non-http, and mistyped fields."""
    with pytest.raises(probatio.Invalid):
        await hass.services.async_call(DOMAIN, SERVICE_SEND, payload, blocking=True)
    assert aioclient_mock.call_count == 0


def test_redact_secrets_covers_header_shapes() -> None:
    """Authorization and Bearer forms lose the token even when the value is copied."""
    text = (
        "failed Authorization: Bearer super-secret-token "
        'and "Proxy-Authorization": "Bearer super-secret-token"'
    )
    redacted = redact_secrets(text, TOKEN)
    assert TOKEN not in redacted
    assert "Bearer ***" in redacted
