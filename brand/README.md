# Brand assets

Neutral mark for Call Webhook: a dot and an arrow leaving it, for an outbound call.

Home Assistant 2026.3+ loads local brand images for custom integrations from
`custom_components/call_webhook/brand/` (PNG only). That folder ships with the
integration. This top-level folder keeps the source SVG and the same PNGs.

| File | Purpose |
|---|---|
| `icon.svg` | Source artwork |
| `icon.png` | 256 × 256 raster used by Home Assistant |
| `icon@2x.png` | 512 × 512 raster |

The PNGs are drawn to match `icon.svg`. Before a HACS default-list submission,
also publish them to [home-assistant/brands](https://github.com/home-assistant/brands).
