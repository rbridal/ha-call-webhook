# Call Webhook for Home Assistant

Send an outbound webhook from an automation or script, using the visual editor.

`rest_command` makes you edit YAML and reload Home Assistant for every new URL. Call Webhook is one integration and one action. Each action carries its own URL, so the next webhook is another action. No YAML is required, and nothing has to be reloaded.

> **Status: 0.1.0.** Requires Home Assistant 2026.11 or newer.

## At a glance

| | |
|---|---|
| Action | **Call Webhook: Send** (`call_webhook.send`) |
| Where | Automations, scripts, and Developer tools → Actions |
| URL | Typed on the action |
| Token | Optional bearer token, typed on the action |
| Body | Optional JSON object. Templates render before the request |
| Install | HACS custom repository, MyHACS, or a manual copy |

## Install

You need Home Assistant 2026.11 or newer.

### HACS custom repository

1. HACS → three-dot menu → **Custom repositories**.
2. Add `https://github.com/rbridal/ha-call-webhook`, category **Integration**.
3. Find **Call Webhook** and download it.
4. Restart Home Assistant if HACS asks you to.

That restart loads the integration. Adding another webhook later does not need one.

### MyHACS

If Call Webhook is already in the household MyHACS catalog, install it from there. The repository is `https://github.com/rbridal/ha-call-webhook`, category Integration. Then restart Home Assistant if MyHACS asks you to.

### Manual

Copy `custom_components/call_webhook` into your Home Assistant `config/custom_components/` folder and restart Home Assistant.

## Add the integration

1. **Settings → Devices & services → Add integration**.
2. Search for **Call Webhook**.
3. Confirm. There is nothing else to enter.

One instance is enough. URLs and tokens are not stored on the integration. They are fields on each action. The **Send** action is available while this entry is loaded. Disabling or removing the entry removes the action.

## Use it in the visual editor

1. Open an automation or script and choose **Add action**.
2. Search for **Call Webhook**. Pick **Call Webhook: Send**. The icon is a webhook.
3. Fill in the fields:

| Field | Required | What it does |
|---|---|---|
| URL | yes | `http` or `https` webhook URL |
| Bearer token | no | Sent as `Authorization: Bearer <token>` when filled in. The box is a password field |
| Data | no | A JSON object. See the template example below |
| Method | no | `POST` (default), `PUT`, `PATCH`, `GET`, or `DELETE` |
| Headers | no | Extra headers, as an object of names and values |
| Timeout | no | Seconds to wait. Default 10, maximum 300 |
| Verify SSL | no | Check the server certificate. Default on |

4. Save the automation. Call it. To hit a different webhook, add another **Call Webhook: Send** action with a different URL. Leave the integration alone.

Developer tools → **Actions** uses the same fields. Choose **Call Webhook: Send**, fill them in, and run it.

### Data and templates

Home Assistant renders templates in the action data before Call Webhook runs. Put the object in the **Data** field:

```yaml
ip: "{{ states('sensor.myip') }}"
location: shop
```

With `sensor.myip` at `203.0.113.10`, the POST body is:

```json
{"ip": "203.0.113.10", "location": "shop"}
```

`Content-Type` is `application/json`. An empty object sends `{}`. Leave Data empty to send no body.

**GET** does not send a body. The same object becomes query parameters: strings and numbers are sent as text, booleans as `true` or `false`, and nested objects or lists as a JSON string. `null` values are left off. A large object belongs on POST, PUT, PATCH, or DELETE, where it is the body.

If **Bearer token** is set, it replaces any `Authorization` header in **Headers**. A JSON body replaces any `Content-Type` header.

## YAML

The same action, including the shop example:

```yaml
action: call_webhook.send
data:
  url: https://hooks.example.com/ingest
  bearer_token: "replace-me"
  data:
    ip: "{{ states('sensor.myip') }}"
    location: shop
```

GET:

```yaml
action: call_webhook.send
data:
  url: https://hooks.example.com/lookup
  method: GET
  data:
    location: shop
```

That requests `https://hooks.example.com/lookup?location=shop`.

## Use the response

Turn on **Response variable** (YAML: `response_variable`) when the automation needs the reply. The variable is an object:

| Key | Value |
|---|---|
| `status` | HTTP status code |
| `ok` | `true` for 2xx |
| `headers` | Response headers. `Authorization` and `Proxy-Authorization` are `***`. Hop-by-hop headers are omitted |
| `body` | Parsed JSON when the body is JSON, otherwise text. Empty is `null` |
| `body_truncated` | Present and `true` when the body was longer than 64 KiB |

```yaml
actions:
  - action: call_webhook.send
    data:
      url: https://hooks.example.com/ingest
      bearer_token: "replace-me"
      data:
        ip: "{{ states('sensor.myip') }}"
        location: shop
    response_variable: webhook_result
  - action: notify.persistent_notification
    data:
      message: >-
        Webhook HTTP {{ webhook_result.status }}
        (ok={{ webhook_result.ok }}): {{ webhook_result.body }}
```

What happens when the call fails:

- **Timeout or connection error.** The action raises an error and stops the automation, including when a response variable was requested.
- **HTTP status outside 2xx.** The action raises an error and stops the automation. With a response variable, it returns `ok: false` and the body instead, so you can branch on `webhook_result.ok`.

The error text includes the method, URL, and status or reason. A bearer token in that text is replaced with `***`.

## Security

A bearer token typed into an action is stored in plain text in `automations.yaml` (or `scripts.yaml`) and in Home Assistant backups. The integration does not keep a copy of it. Debug logs and error messages redact the token and the `Authorization` header. The request on the wire still sends `Authorization: Bearer <token>`.

Treat an automation export, a dashboard trace, and a backup as copies of that token. Prefer a token you can revoke, and leave **Verify SSL** on unless you trust the certificate path.

## Removing it

1. **Settings → Devices & services → Call Webhook → Delete.**
2. Remove it from HACS or MyHACS, or delete `custom_components/call_webhook`, and restart Home Assistant.

Automations that still call `call_webhook.send` will fail once the action is gone.

## Development

Python 3.14 or newer. From a checkout:

```bash
pip install -r requirements_test.txt
ruff check .
pytest
```

Tests run against Home Assistant 2026.11 via `pytest-homeassistant` (the package that replaced `pytest-homeassistant-custom-component` for this Core version).

## License

MIT. See [LICENSE](LICENSE).
