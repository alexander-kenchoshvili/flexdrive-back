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

## Wingo delivery

Wingo is the active courier. Checkout reads local reference data; refresh it manually
from the Wingo tariffs admin after configuring the account. No tariff polling job.

```env
WINGO_API_KEY=<backend-only encrypted secret>
WINGO_ACCOUNT_MODE=test
WINGO_API_BASE_URL=https://www.apiwingo.com/api/v1
WINGO_MERCHANT_USER_ID=<merchant internal ID>
WINGO_PICKUP_TITLE=<company name>
WINGO_PICKUP_ADDRESS=<pickup address>
WINGO_PICKUP_PHONE=<pickup phone>
WINGO_WEBHOOK_PUBLIC_URL=<public backend Wingo webhook prefix>
WINGO_PREPARATION_MINUTES=30
DELIVERY_QUOTE_MAX_AGE_SECONDS=900
```

Use the real merchant key/ID and `production` mode for launch, then refresh references
again. Account mode is an operator label; the key selects the provider account.
`WINGO_WEBHOOK_PUBLIC_URL` must end in `/api/commerce/wingo/webhook/` on the public
HTTPS backend. Each order gets a private authenticated callback URL. Canonical GET
verification and the manual admin status button share the same tracking flow.
There is no courier cron job. Remove retired courier jobs and unused old credentials
from deployment settings; this source change does not edit the deployed environment.

Only a staff operator books paid/prepared shipments. Cancellation and reverse booking
happen in Wingo's panel, bank refunds stay in our admin after verification/receipt.
Receipt seller data remains configured through `ORDER_RECEIPT_SELLER_*`.
See [Wingo checkout](WINGO_CHECKOUT.md), [outbound labels](WINGO_OUTBOUND.md),
[tracking](WINGO_TRACKING.md), [manual returns](WINGO_PLATFORM_RETURNS.md), and
[retirement/reporting](WINGO_REPORTING_CLEANUP.md).

## Meta Purchase delivery

Eligible Meta Purchase events are sent directly after the related database
transaction commits. Meta delivery failures are logged and never roll back or
break the order update. No Meta worker or Cron Job is required.
