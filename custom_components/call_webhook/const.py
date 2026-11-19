"""Constants for the Call Webhook integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "call_webhook"
INTEGRATION_NAME: Final = "Call Webhook"

SERVICE_SEND: Final = "send"

CONF_URL: Final = "url"
CONF_BEARER_TOKEN: Final = "bearer_token"
CONF_DATA: Final = "data"
CONF_METHOD: Final = "method"
CONF_HEADERS: Final = "headers"
CONF_TIMEOUT: Final = "timeout"
CONF_VERIFY_SSL: Final = "verify_ssl"

DEFAULT_METHOD: Final = "POST"
DEFAULT_TIMEOUT: Final = 10
DEFAULT_VERIFY_SSL: Final = True

HTTP_METHODS: Final = ("POST", "PUT", "PATCH", "GET", "DELETE")

# Response bodies larger than this are truncated before they are returned
# to an automation or included in an error.
MAX_BODY_BYTES: Final = 65_536
MAX_ERROR_BODY_CHARS: Final = 300

ATTR_STATUS: Final = "status"
ATTR_OK: Final = "ok"
ATTR_HEADERS: Final = "headers"
ATTR_BODY: Final = "body"
ATTR_BODY_TRUNCATED: Final = "body_truncated"
