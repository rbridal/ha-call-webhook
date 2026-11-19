"""Send one outbound webhook and build a response automations can use.

GET sends ``data`` as query parameters and does not send a body. POST, PUT,
PATCH, and DELETE JSON-encode ``data`` as the body with
``Content-Type: application/json``.

A network error or a timeout always raises ``HomeAssistantError``. An HTTP
status outside 2xx does too, unless the caller asked for a response
(``response_variable`` / ``return_response``). In that case the action returns
``status``, ``ok``, ``headers``, and ``body`` and the automation decides what
to do.

The bearer token and the Authorization header are redacted in debug logs and
in error messages. The request itself still sends them.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
import re
from typing import Any

import aiohttp
from homeassistant.const import CONTENT_TYPE_JSON
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.json import json_dumps
from homeassistant.util.json import JSON_DECODE_EXCEPTIONS, json_loads
import probatio

from .const import (
    ATTR_BODY,
    ATTR_BODY_TRUNCATED,
    ATTR_HEADERS,
    ATTR_OK,
    ATTR_STATUS,
    CONF_BEARER_TOKEN,
    CONF_DATA,
    CONF_HEADERS,
    CONF_METHOD,
    CONF_TIMEOUT,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_METHOD,
    DEFAULT_TIMEOUT,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    HTTP_METHODS,
    MAX_BODY_BYTES,
    MAX_ERROR_BODY_CHARS,
)

_LOGGER = logging.getLogger(__name__)

_AUTH_HEADER = "authorization"
_PROXY_AUTH_HEADER = "proxy-authorization"
_REDACTED_HEADER_NAMES = frozenset({_AUTH_HEADER, _PROXY_AUTH_HEADER})

# Bearer tokens show up as a header, as "Bearer <token>", and sometimes copied
# into the exception text aiohttp raises. Strip those shapes. The token string
# itself is also removed when it is long enough to be unambiguous.
_AUTH_PATTERNS = (
    re.compile(
        r"(?i)(\b(?:proxy-)?authorization['\"]?\s*[:=]\s*['\"]?(?:bearer\s+)?)([^\s'\",}]+)"
    ),
    re.compile(r"(?i)(\bBearer\s+)(\S+)"),
)
_MIN_BLIND_REDACT = 4

_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "te",
        "trailer",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)


def redact_secrets(text: str, *secrets: str | None) -> str:
    """Remove bearer tokens and Authorization values from text."""
    redacted = text
    for secret in secrets:
        if secret and len(secret) >= _MIN_BLIND_REDACT:
            redacted = redacted.replace(secret, "***")
    for pattern in _AUTH_PATTERNS:
        redacted = pattern.sub(r"\1***", redacted)
    return redacted


def _header_name(value: Any) -> str:
    """Validate a request header name."""
    name = str(value).strip()
    if not name or any(char in name for char in "\r\n\x00:"):
        raise probatio.Invalid("invalid header name")
    return name


def _header_value(value: Any) -> str:
    """Coerce a header value to text."""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int | float):
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise probatio.Invalid("header values must be text, numbers, or booleans")
    if any(char in text for char in "\r\n\x00"):
        raise probatio.Invalid("header values cannot contain newlines")
    return text


def _bearer_token(value: Any) -> str:
    """Normalize an optional bearer token. Blank means unset."""
    if value is None:
        return ""
    text = str(value).strip()
    if any(char in text for char in "\r\n\x00"):
        raise probatio.Invalid("bearer token cannot contain newlines")
    return text


def _data_object(value: Any) -> dict[str, Any]:
    """Require a JSON object. Templates have already been rendered."""
    if not isinstance(value, dict):
        raise probatio.Invalid("data must be a JSON object")
    if any(not isinstance(key, str) for key in value):
        raise probatio.Invalid("data keys must be strings")
    return value


def _method(value: Any) -> str:
    """Normalize an HTTP method."""
    method = str(value).strip().upper()
    if method not in HTTP_METHODS:
        raise probatio.Invalid(f"method must be one of {', '.join(HTTP_METHODS)}")
    return method


SEND_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_URL): cv.url,
        probatio.Optional(CONF_BEARER_TOKEN): _bearer_token,
        probatio.Optional(CONF_DATA): _data_object,
        probatio.Optional(CONF_METHOD, default=DEFAULT_METHOD): _method,
        probatio.Optional(CONF_HEADERS): {_header_name: _header_value},
        probatio.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): probatio.All(
            probatio.Coerce(float),
            probatio.Range(min=1, max=300),
        ),
        probatio.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
    }
)


def _query_value(value: Any) -> str | None:
    """Encode one JSON value as a query parameter."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    return json_dumps(value)


def _query_params(data: Mapping[str, Any]) -> dict[str, str]:
    """Turn a data object into query parameters for GET."""
    params: dict[str, str] = {}
    for key, value in data.items():
        encoded = _query_value(value)
        if encoded is None:
            continue
        params[str(key)] = encoded
    return params


def _logged_headers(headers: Mapping[str, str], *secrets: str | None) -> dict[str, str]:
    """Copy headers with Authorization removed."""
    safe: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _REDACTED_HEADER_NAMES:
            safe[key] = "***"
        else:
            safe[key] = redact_secrets(value, *secrets)
    return safe


def _response_headers(
    headers: Mapping[str, str], *secrets: str | None
) -> dict[str, str]:
    """Return response headers, dropping hop-by-hop fields and redacting auth."""
    safe: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in _HOP_BY_HOP:
            continue
        if lowered in _REDACTED_HEADER_NAMES:
            safe[key] = "***"
        else:
            safe[key] = redact_secrets(str(value), *secrets)
    return safe


def _parse_body(raw: bytes, content_type: str | None, truncated: bool) -> Any:
    """Parse JSON when the body looks like JSON, otherwise return text."""
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text = f"{text}…[truncated]"
    media = (content_type or "").lower()
    looks_like_json = "json" in media or text.lstrip()[:1] in {"{", "["}
    if looks_like_json and not truncated:
        try:
            return json_loads(text)
        except JSON_DECODE_EXCEPTIONS:
            return text
    return text


def _snippet(body: Any, *secrets: str | None) -> str:
    """Short redacted body for an error message."""
    if body is None:
        text = "no response body"
    elif isinstance(body, str):
        text = body
    else:
        text = json_dumps(body)
    text = redact_secrets(text, *secrets)
    if len(text) > MAX_ERROR_BODY_CHARS:
        return f"{text[:MAX_ERROR_BODY_CHARS]}…"
    return text


def _format_seconds(value: float) -> str:
    """Format a timeout without a trailing .0."""
    if value.is_integer():
        return str(int(value))
    return str(value)


def _fail(
    translation_key: str,
    message: str,
    placeholders: dict[str, str],
) -> HomeAssistantError:
    """Build an error whose text and translation placeholders are already redacted."""
    return HomeAssistantError(
        message,
        translation_domain=DOMAIN,
        translation_key=translation_key,
        translation_placeholders=placeholders,
    )


async def async_handle_send(call: ServiceCall) -> ServiceResponse:
    """Handle call_webhook.send."""
    data = call.data
    token = data.get(CONF_BEARER_TOKEN) or None
    return await async_send(
        call.hass,
        url=data[CONF_URL],
        method=data[CONF_METHOD],
        payload=data.get(CONF_DATA),
        headers=data.get(CONF_HEADERS) or {},
        bearer_token=token,
        timeout=float(data[CONF_TIMEOUT]),
        verify_ssl=bool(data[CONF_VERIFY_SSL]),
        return_response=call.return_response,
    )


async def async_send(
    hass: HomeAssistant,
    *,
    url: str,
    method: str,
    payload: dict[str, Any] | None,
    headers: Mapping[str, str],
    bearer_token: str | None,
    timeout: float,
    verify_ssl: bool,
    return_response: bool,
) -> ServiceResponse:
    """Perform the HTTP request."""
    token = bearer_token or None
    outgoing = {str(key): str(value) for key, value in headers.items()}
    params: dict[str, str] | None = None
    json_body: dict[str, Any] | None = None

    if method == "GET":
        if payload is not None:
            params = _query_params(payload)
    elif payload is not None:
        json_body = payload
        outgoing = {
            key: value for key, value in outgoing.items() if key.lower() != "content-type"
        }
        outgoing["Content-Type"] = CONTENT_TYPE_JSON

    if token:
        outgoing = {
            key: value for key, value in outgoing.items() if key.lower() != _AUTH_HEADER
        }
        outgoing["Authorization"] = f"Bearer {token}"
    authorization = next(
        (value for key, value in outgoing.items() if key.lower() == _AUTH_HEADER),
        None,
    )

    secrets = tuple(secret for secret in (token, authorization) if secret)
    safe_url = redact_secrets(url, *secrets)
    _LOGGER.debug(
        "Sending webhook %s %s verify_ssl=%s timeout=%s headers=%s",
        method,
        safe_url,
        verify_ssl,
        _format_seconds(timeout),
        _logged_headers(outgoing, *secrets),
    )

    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    request_kwargs: dict[str, Any] = {
        "headers": outgoing,
        "timeout": aiohttp.ClientTimeout(total=timeout),
    }
    if params:
        request_kwargs["params"] = params
    if json_body is not None:
        request_kwargs["json"] = json_body

    try:
        async with session.request(method, url, **request_kwargs) as response:
            status = response.status
            # Bind the stream once. The test double builds a new stream on
            # every access of ``response.content``.
            content = response.content
            chunks: list[bytes] = []
            remaining = MAX_BODY_BYTES + 1
            while remaining:
                block = await content.read(remaining)
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            raw = b"".join(chunks)
            content_type = response.headers.get("Content-Type")
            response_headers = _response_headers(response.headers, *secrets)
    except TimeoutError:
        message = (
            f"Timed out calling {method} {safe_url} after {_format_seconds(timeout)} seconds."
        )
        _LOGGER.debug("%s", message)
        # Drop the original exception. aiohttp includes the request URL, and
        # that URL can contain the token.
        raise _fail(
            "timeout",
            message,
            {
                "method": method,
                "url": safe_url,
                "timeout": _format_seconds(timeout),
            },
        ) from None
    except aiohttp.ClientError as err:
        safe_error = redact_secrets(str(err), *secrets)
        message = f"Could not call {method} {safe_url}: {safe_error}"
        _LOGGER.debug("%s", message)
        raise _fail(
            "request_failed",
            message,
            {"method": method, "url": safe_url, "error": safe_error},
        ) from None

    truncated = len(raw) > MAX_BODY_BYTES
    if truncated:
        raw = raw[:MAX_BODY_BYTES]
    body = _parse_body(raw, content_type, truncated)
    ok = 200 <= status < 300
    _LOGGER.debug("Webhook %s %s returned HTTP %s", method, safe_url, status)

    result: dict[str, Any] = {
        ATTR_STATUS: status,
        ATTR_OK: ok,
        ATTR_HEADERS: response_headers,
        ATTR_BODY: body,
    }
    if truncated:
        result[ATTR_BODY_TRUNCATED] = True

    if ok or return_response:
        if return_response:
            return result
        return None

    snippet = _snippet(body, *secrets)
    message = f"{method} {safe_url} returned HTTP {status}: {snippet}"
    raise _fail(
        "http_status",
        message,
        {
            "method": method,
            "url": safe_url,
            "status": str(status),
            "body": snippet,
        },
    )
