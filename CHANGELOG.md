# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-19

First release. Requires Home Assistant 2026.11.0 or newer.

### Added

- Call Webhook custom integration (`call_webhook`), added from the UI. One instance.
- Action **Call Webhook: Send** (`call_webhook.send`), registered when the config entry loads, with visual-editor selectors for URL, bearer token, data, method, headers, timeout, and verify SSL.
- JSON body for POST, PUT, PATCH, and DELETE. GET sends the data object as query parameters.
- Optional response data (`status`, `ok`, `headers`, `body`) for `response_variable`.
- Timeouts, connection errors, and non-2xx responses raise `HomeAssistantError`. A non-2xx response is returned instead when the caller asked for a response.
- Bearer token and `Authorization` redaction in debug logs and error messages.
- HACS metadata, brand icon, and CI for pytest, hassfest, and HACS validation.

[0.1.0]: https://github.com/rbridal/ha-call-webhook/releases/tag/v0.1.0
