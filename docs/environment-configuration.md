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

## EasyWay delivery quotes

Regional checkout pricing is returned by EasyWay's `/price` endpoint. The
backend adds the configured customer margin and signs a short-lived quote so the
frontend cannot alter delivery totals.

```env
EASYWAY_API_USER=<EasyWay user ID>
EASYWAY_API_KEY=<EasyWay API key>
EASYWAY_API_BASE_URL=https://easyway.ge/api
EASYWAY_SENDER_NAME=<company name>
EASYWAY_SENDER_TAX_CODE=<company tax code>
EASYWAY_SENDER_ADDRESS=<courier pickup address>
EASYWAY_SENDER_PHONE=<courier pickup contact phone>
EASYWAY_SENDER_REGION_ID=24
EASYWAY_SENDER_CITY_ID=<EasyWay city ID for the real pickup location>
EASYWAY_SENDER_LEGAL_FORM_ID=3
EASYWAY_RECEIVER_TAX_CODE_PLACEHOLDER=11111111111
EASYWAY_STANDARD_PACKAGE_ID=2
EASYWAY_DELIVERY_MARGIN_GEL=2.00
EASYWAY_INTERNAL_DELIVERY_PRICE_GEL=0.00
EASYWAY_QUOTE_MAX_AGE_SECONDS=900
```

`EASYWAY_SENDER_CITY_ID` is mandatory for regional quotes and must not be
guessed: it is the EasyWay city ID corresponding to FlexDrive's real pickup
location. Tbilisi/internal delivery does not call EasyWay and currently returns
zero delivery cost.

## Meta Purchase delivery

Eligible Meta Purchase events are sent directly after the related database
transaction commits. Meta delivery failures are logged and never roll back or
break the order update. No Meta worker or Cron Job is required.
