# FlexDrive business panel prototype

Design source: paired frontend, read on 2026-10-08.

- Tokens: `flexdrivefront/app/assets/css/design-system.css`, copied without changing the palette.
- Typeface: local Noto Sans Georgian Regular, Medium, SemiBold and Bold from `app/assets/fonts`, embedded as WOFF2 data URLs.
- Logo: existing `NewFlexdriveLogoHorizontal.vue`; its original SVG geometry and on-dark palette are embedded as an SVG image data URL. No redrawn logo.
- Interface reference: existing header/component source and `docs/design-system-foundation.md`. No live site or customer data accessed.
- Primary layout: dark green navigation, calm light workspace, an editorial KPI strip, large period chart and contextual explanations. Numbers take priority over decoration.
- Variations: comfortable light, comfortable dark, compact light. Theme/density are local prototype settings.
- All financial/traffic/search/social examples are synthetic, visibly labeled. No data source, authentication, scheduler or API connection is implemented.
- Georgian labels, GEL, completed July–September demo periods; comparisons use complete previous months.
- Standalone deliverable: one HTML with embedded CSS, JS, fonts and logo; no external resources or network calls.
- Scope: design review, not a production route or access-control implementation.

Assumptions: owner-facing desktop dashboard, mobile fallback, visual and interaction review of one coherent direction. Existing user instructions prohibit unsolicited browser/server checks; use static validation and let the user open the delivered file.
