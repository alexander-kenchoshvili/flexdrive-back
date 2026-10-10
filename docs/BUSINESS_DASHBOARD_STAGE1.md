# Business dashboard — stage 1 checkpoint

Date: 2026-10-09. Code is ready for user review; stage 2 has not started.

## Implemented

- Private frontend `/business` and five section routes, Georgian login and dashboard shell adapted from the approved prototype using existing fonts, tokens, light/dark themes and responsive sizing.
- Existing administrator username/password, with an independent HttpOnly business session. Storefront JWTs and Django admin sessions are neither reused nor replaced. Active staff plus `business.view_dashboard`, or active superuser, is required on every protected API request.
- Fresh reCAPTCHA v3 action `business_login` for each submission, existing server-side verification, CSRF protection and IP/account throttles. Private responses are not cacheable.
- Login/session/access/logout APIs under `/api/business/`. Logout invalidates the business session; password changes, deactivation and permission revocation deny further access.
- Private routes excluded from public analytics, sitemap and indexing. Crossing the storefront/business boundary reloads the document to avoid retaining storefront GTM listeners.
- Honest disconnected placeholders: no prototype numbers, invented trends or external reports. No statistics have been connected yet, and ECharts is deferred until real graphs are needed.

## Checks completed

- 30 backend tests: 17 dashboard tests plus existing account session/CSRF tests, using disposable in-memory SQLite and mocked CAPTCHA. No real bank/provider requests or orders.
- 30 frontend tests: 12 dashboard tests plus existing header-search and checkout-draft tests.
- Focused ESLint, Nuxt typecheck and local `npm run build` passed. This build is only compilation on this computer; nothing was uploaded or deployed.
- Migration drift check and tracked-file whitespace checks passed.

No server or browser was started for this stage. Visual layout, actual browser cookie/proxy behavior and real reCAPTCHA acceptance still require user review.

## Review

1. Start the usual local backend and frontend. Open `/business` on that frontend (normally `https://localhost:3000/business`).
2. Use the administrator account belonging to this same backend environment. A production account does not automatically exist in the local database. No account/password/permission has been created or changed.
3. Review login, six navigation sections, light/dark appearance and narrow screen layout. Empty statistics are intentional at this stage.
4. While signed into the storefront separately, enter and leave the dashboard; the storefront login should stay active. Refresh checks dashboard access again.

`business.0001_initial` introduces only the unmanaged permission model state; no business data table is created. It was applied only in disposable test databases, not the real local database, staging or production. An active superuser passes the capability check automatically. Ordinary staff needs the permission migration and an explicitly granted `business.view_dashboard` permission before access; no such grant has been performed.

The existing reCAPTCHA keys/settings are reused without edits. If the local hostname is not accepted by their current configuration, stop and clarify the configuration with the user; do not bypass CAPTCHA or change credentials silently.

Stop after review delivery. Continue with real sales/finance data only after the user's next-stage instruction. Work remains in the ordinary project folders; no branch/worktree, remote changes, real integration calls or scheduler were introduced.

## Logout review fix — 2026-10-09

User reported logout stuck at the layout's access-check placeholder and authorized this fix only. The layout now selects the login branch from `useRouter().currentRoute`, because Nuxt's `useRoute()` waits for destination page rendering while the cleared-user branch had removed that page slot. Added a regression test rendering the actual layout template with the old Nuxt page route deliberately delayed: after logout, the login form mounts and private content disappears. All 13 dashboard frontend tests, typecheck and focused lint passed. No browser check was run; user resumes manual review. At this checkpoint, promotional login copy removal and conversion from `business.css` to Tailwind were deferred by the user.

## Tailwind and login simplification — 2026-10-09

User then explicitly authorized removing the promotional left-hand login block and replacing all dashboard-specific CSS with Tailwind. Login now has one centered form using the existing BaseInput/BaseButton components. Layout, dashboard sections, responsive sidebar and native source dialog use inline Tailwind utilities and existing theme tokens; `app/assets/css/business.css` and its import were removed, with no replacement stylesheet or style block. Mobile-menu focus uses a data attribute instead of the deleted CSS class. Auth/session/CAPTCHA behavior and the logout fix are preserved.

All 13 dashboard tests, typecheck, focused lint and local build passed. Verified all 293 static Tailwind utilities in the three updated templates exist in the compiled CSS. Browser/visual review remains with the user; no server/browser or remote deployment was started. Continue waiting for review before stage 2.
