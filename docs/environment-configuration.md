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

## Outbound task worker

Meta Purchase tasks are stored in the database and retried automatically by:

```bash
python manage.py process_outbound_tasks --limit 100
```

Configure this as a Render Cron Job that runs every minute.
