# Environment configuration

FlexDrive uses `APP_ENV` to distinguish runtime environments:

- `development` — local development; this is the default outside managed hosting.
- `staging` — deployed test environment.
- `production` — future live environment.

Managed Render services must set `APP_ENV` explicitly.

## Local development

Recommended local values:

```env
APP_ENV=development
DJANGO_DEBUG=True
CACHE_ENABLED=False
```

When Redis is disabled, Django uses separate in-process `LocMemCache` instances
for application caching and API throttling. This keeps rate limiting testable
while running the local development server.

## Staging

Required backend values:

```env
APP_ENV=staging
DJANGO_DEBUG=False
CACHE_ENABLED=True
CACHE_REDIS_URL=<Render Redis internal URL>
FRONTEND_BASE_URL=https://flexdrive-front.vercel.app
DJANGO_ALLOWED_HOSTS=flexdrive-back.onrender.com
CORS_ALLOWED_ORIGINS=https://flexdrive-front.vercel.app
CSRF_TRUSTED_ORIGINS=https://flexdrive-front.vercel.app
```

`DJANGO_SECRET_KEY` must contain a non-development secret. Secure cookies and
HTTPS redirect must remain enabled. The application refuses to start if a
deployed environment is missing required security or Redis configuration.

## Production

Use the same requirements as staging with production-specific domains, secrets,
database, Redis, email, media storage, OAuth and external-service credentials.
No code changes should be required when production is introduced.

Never commit environment files, passwords, private URLs or API tokens.

## Bank of Georgia card payments

BOG card payments remain disabled unless explicitly enabled:

```env
BOG_PAYMENTS_ENABLED=False
BOG_CLIENT_ID=<BOG dashboard Public Key>
BOG_CLIENT_SECRET=<BOG dashboard Secret Key>
BOG_OAUTH_URL=https://oauth2.bog.ge/auth/realms/bog/protocol/openid-connect/token
BOG_API_BASE_URL=https://api.bog.ge
BOG_CALLBACK_PUBLIC_URL=https://<backend-domain>/api/commerce/payments/bog/callback/
BOG_FRONTEND_SUCCESS_URL=https://<frontend-domain>/checkout/payment/success
BOG_FRONTEND_FAIL_URL=https://<frontend-domain>/checkout/payment/fail
BOG_HTTP_CONNECT_TIMEOUT_SECONDS=5
BOG_HTTP_READ_TIMEOUT_SECONDS=15
BOG_TOKEN_REFRESH_SKEW_SECONDS=30
BOG_ORDER_TTL_MINUTES=15
BOG_STOCK_RESERVATION_TTL_SECONDS=1020
BOG_CALLBACK_MAX_BODY_BYTES=262144
```

`BOG_CLIENT_SECRET` is a deployment secret. It must never be placed in frontend
configuration, committed files, logs, screenshots, or support messages.

`BOG_CALLBACK_PUBLIC_KEY` may override the official BOG callback verification
key if the bank rotates it. Store multiline PEM values through the deployment
secret/configuration interface; escaped `\n` line breaks are supported.

When `BOG_PAYMENTS_ENABLED=True`, backend startup requires both credentials,
valid HTTPS provider/customer-return URLs, and positive timeout values. Stock
reservation must remain active longer than the BOG order; the default adds a
two-minute safety margin to the 15-minute payment window.

Keep the flag disabled on public staging/production checkout until refund/admin,
frontend, and controlled real-environment verification are complete. A browser
redirect is never proof that payment succeeded; only the signed callback or an
authenticated BOG payment-details response may finalize payment.

## Cross Motors delayed stock protection

Cross Motors stock refreshes preserve a temporary local deduction for recently
completed FlexDrive sales. The default protection window is 24 hours:

```env
CROSSMOTORS_SALE_HOLD_SECONDS=86400
```

Keep the supplier cron running every 15 minutes. A successful import records the
raw supplier quantity separately and calculates effective stock after active
local deductions. Expired deductions are retired only during a successful
supplier import, so an unavailable supplier API cannot increase customer-facing
stock from stale data.

The protection window can be tuned after measuring the real Cross Motors update
delay. Do not reduce it below the observed worst-case delay without retaining an
appropriate safety margin.

## RedCap delivery

RedCap replaces EasyWay and internal Tbilisi delivery for new checkouts.
Customer fees are calculated from the locally stored tariff table using summed
packaged product weight. Parcel count does not multiply the tariff; dimensions
and volumetric weight do not affect pricing. There is no customer margin yet.

```env
REDCAP_API_KEY=<backend-only secret>
REDCAP_API_BASE_URL=https://redcap.ge/api/v1
REDCAP_HTTP_CONNECT_TIMEOUT_SECONDS=5
REDCAP_HTTP_READ_TIMEOUT_SECONDS=15
REDCAP_SENDER_NAME=<company name>
REDCAP_SENDER_PHONE=<pickup phone>
REDCAP_SENDER_CITY=<exact RedCap location name>
REDCAP_SENDER_ADDRESS=<actual pickup address>
DELIVERY_QUOTE_MAX_AGE_SECONDS=900
```

Apply commerce migrations 0037/0038 and initially refresh references from admin
or `python manage.py refresh_redcap_references`. Checkout never contacts RedCap
for an address selection. Subsequent tariff refreshes are manual after notice;
no daily tariff cron. A missing product weight or tariff blocks the quote.
Existing category measurement defaults are not used.

Only a staff operator creates a shipment after payment and packaging. Credentials
remain on the backend. Configure receipt seller data explicitly through
`ORDER_RECEIPT_SELLER_*`; there is no EasyWay sender fallback.

Disable the old EasyWay job. RedCap tracking uses
`python manage.py sync_redcap_tracking --limit 100 --min-age-minutes 10`
in the existing appropriate scheduled execution environment. No infrastructure
or runtime environment was changed by the source implementation.
See [REDCAP_INTEGRATION.md](REDCAP_INTEGRATION.md) for coordinated frontend/backend
activation, operator printing and remaining live verification.

## Meta Purchase delivery

Eligible Meta Purchase events are sent directly after the related database
transaction commits. Meta delivery failures are logged and never roll back or
break the order update. No Meta worker or Cron Job is required.
