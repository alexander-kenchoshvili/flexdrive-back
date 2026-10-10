# Project Instructions

## Browser Analytics Isolation Completed - 2026-10-10

- User authorized frontend host isolation. Shared exact flexdrive.ge hostname
  guard blocks GTM initialization and ecommerce/search events on local, staging,
  www and temporary hosting domains, even with tracking consent. Existing consent
  and private-business guards retained; dashboard read access remains independent.
- 35 focused frontend tracking/search/business tests, typecheck and scoped lint
  pass. User handles push/deploy. No browser/server start, secret or provider edit,
  real payment or production changes. Supersedes earlier browser isolation pending
  notes; final-domain event delivery and purchase dedup are still unverified.

## Dashboard User Checkpoint And Deferred Verification - 2026-10-10

- User confirms the local Google dashboard now works after the focused start.ps1
  dotenv-loader fix. Startup uses the existing python-dotenv parser; all env values
  and actual GA4 credential loading verified without exposing secrets or starting
  a server. User keeps the same startup workflow.
- Staging Render backend has the existing CAPI token and Pixel 1020718363721235.
  User confirms production CAPI variables were saved and deployed, and staging
  META_CAPI_ENABLED was changed to false. Supersedes older missing-production-env
  audit notes; actual purchase delivery and token validity are not yet verified.
- User will push/deploy dashboard code himself; completion is not yet confirmed.
  User explicitly defers purchase testing until another time. Do not initiate a
  payment, create a paid order, or claim browser/server deduplication verified.
- Staging CAPI disabled does NOT prove browser Pixel/GTM environment isolation.
  Keep browser tracking isolation and cart/purchase delivery checks outstanding.
- At restricted flexdrive.ge cutover: verify Search Console and connect GA4;
  verify Meta domain and domain-dependent Pixel settings; activate/verify canonical
  flexdrive.ge and www redirect, GA4 scope and GTM/domain configuration; verify
  consent, event delivery, company SKUs/values and browser/server purchase dedup.
  Preserve the separate existing domain/provider and reconciliation checklist.

## Pixel/CAPI Current Audit - 2026-10-10

- User authorized current audit; domain verification deferred with Search Console.
  Live GTM public script has correct Pixel/AddToCart/Purchase/eventID forwarding;
  frontend/server purchase IDs match. Meta overview still shows only older browser
  PageView/ViewContent, not server/cart/purchase proof.
- Local CAPI disabled, Pixel setting absent, no CAPI token/test code. Reporting
  reader token must NOT be reused for CAPI. Production DO service41/app-level31
  variable-name fields inspected read-only: all three CAPI config names absent.
  Secret values were not output; no Save/Cancel/deploy. Deployed process not read.
- User-running local storefront cart add worked. Added one FD-08-0127 then removed
  only that line; original FD-04-0669 x1/65 GEL retained. Original optional consent
  all-false restored after test. No checkout/order/provider requests or new server.
- Meta Test Events did not activate local URL/receive a visible cart test. Runtime
  network inspection unavailable. Do NOT claim real AddToCart/Purchase/dedup proved.
- Five internal-SKU tests passed; three old Meta tests failed during legacy fixture
  setup on published-SKU constraint. Five in-memory mocked purchase/consent checks
  passed; no real transport or business DB writes. No legacy fixture repair.
- See docs/META_PIXEL_CAPI_AUDIT.md. Next coordinate CAPI config and an agreed test
  scenario with user; no new credentials/env edits/fake paid records on own initiative.

## Meta Domain Cutover Deferred By User - 2026-10-10

- User explicitly requests recording Meta flexdrive.ge domain verification and
  domain-dependent Pixel configuration alongside Search Console at domain cutover.
  Do not perform domain/DNS/allowlist edits before that stage. Restricted-access
  cutover requirements remain in force. User separately requests Pixel/CAPI audit
  now; this supersedes earlier audit deferral only for current verification work.

## Meta Dashboard Connector - 2026-10-10

- User authorized dashboard connection; production variable will be entered by
  user. BUSINESS_META_ACCESS_TOKEN is now consumed by local backend; supersedes
  older preparation-only status below. Do not generate another token or change
  customer login/CAPI credentials. No push/deploy or production env edit performed.
- Protected business/marketing endpoint reads only the fixed FlexDrive Page, IG
  and ad account via Graph v26.0. Page insights use a transient derived Page token.
  Ads currency/timezone come from account; USD is not relabeled/converted to GEL.
  Whole-period reach stays distinct from daily sums; website purchase attribution
  is 7d_click/1d_view by conversion date, not financial ledger sales.
- Independent five-minute source caches, bounded reads/pagination/backoff, stale
  snapshots with original timestamps and explicit missing/failed/range states.
  Facebook maximum90/IG maximum30-day activity ranges; current profiles remain
  available. No cron/job, data/schema write or bank/carrier/supplier requests.
- Paired frontend marketing page uses Georgian Tailwind/design tokens, Lazy modular
  ECharts cost chart, campaign/social stats, observed-fact summary and existing
  business auth. Period changes/unmount abort old requests. Secrets stay server-side.
- 70 full business tests passed; final Meta consistency change passed 11 focused
  tests. Frontend47 business tests, typecheck/scoped ESLint and production build
  passed. Details in docs/BUSINESS_DASHBOARD_STAGE5.md.
- Actual new connector returned ready for Oct1-10: FB followers3, ten complete
  days zero views/interactions; IG followers0/reach0/views0/interactions0; Ads empty,
  USD, no campaigns. No demo data. Active campaigns/nonzero stats and visual browser
  checks remain; user review is next. No servers/browser started for this work.
- User must add only backend Runtime secret BUSINESS_META_ACCESS_TOKEN using its
  existing complete local .env value. Works in production after code deploy.
  Domain verification/ecommerce delivery/deduplication remain separate later work.

## Meta Reporting Token Ready - 2026-10-10

- User explicitly confirmed Never expiry after automatic review's earlier block.
  Generated ONE token for FlexDrive Analytics 1432926452359920 and Employee reader
  61594899706565. Selected exactly ads_read, instagram_basic,
  instagram_manage_insights, pages_read_engagement, pages_show_list, read_insights.
- Stored only BUSINESS_META_ACCESS_TOKEN in backend ignored local .env; no secret
  output/artifact, app secret read, production config change, push or deployment.
  Token dialog closed only after verified local file write. Do not generate again.
- Reload verified four assets: Page/Instagram Insights, ad account View performance,
  analytics app View insights + auto Test app. No management/content/message grants.
- Actual read-only Graph v23.0 calls all returned HTTP 200: Page ID 1044408968766868
  followers=3 and links IG 17841432881478668; IG username flexdrive.ge followers=0,
  media_count=0; ad account 1462913205812039 active USD Asia/Tbilisi. Oct1-10 ad
  insights spend/impressions/clicks returned genuine zero rows. No provider writes.
- A first probe output hit Windows stdout Unicode encoding; the corrected ASCII
  JSON probe succeeded. No secret was printed in either run. Page/IG time-series
  insights, production credential configuration and dashboard connector/UI remain
  NEXT work; current token is not consumed by application code yet. Existing CAPI
  user/credentials and customer login app unchanged.
- Proof: artifacts/analytics/meta-reporting-reader-ready.png.

## Meta Reporting Reader Created - 2026-10-10

- User explicitly confirmed non-discrimination policy acceptance, reader creation,
  reporting asset access and token generation. Policy accepted; created Employee
  FlexDrive Analytics Reader 61594899706565 in flexdrive.ge portfolio.
- Added optional app read_insights, instagram_basic, instagram_manage_insights;
  Ready for testing observed. Selected Facebook/linked IG Insights, ad account
  View performance, reporting app View insights (auto Test app). Meta success
  dialog confirmed four assets assigned. No content/messages/ads-management grants.
- Prepared token for app 1432926452359920 with ads_read, instagram_basic,
  instagram_manage_insights, pages_read_engagement, pages_show_list, read_insights.
  Never expiry selected, but automatic review rejected generation because user
  had not explicitly confirmed permanent expiry. NO TOKEN GENERATED/STORED.
- Expiry confirmation requested; browser left on Never/60-day step. Returning
  from the open permissions overlay accidentally deselected pages_show_list in
  the draft; MUST restore and verify all six scopes before eventual generation.
  Do not generate temporary token as a workaround for permanent-expiry rejection.
- Existing CAPI user/token, old login app, billing, ads and code unchanged.
  Proof: artifacts/analytics/meta-reporting-token-expiry-confirm.png.

## Meta Reporting App Preparation - 2026-10-10

- Instagram reauthentication completed: Login needed disappeared, Insights access
  remains available. User approved separate FlexDrive ad account: 1462913205812039,
  owned by flexdrive.ge, USD, Asia/Tbilisi. Created successfully; no billing or ads.
- User approved Meta Platform Terms/Developer Policies and completed Facebook
  password reauthentication. Created FlexDrive Analytics app 1432926452359920 with
  Marketing API ad performance, Instagram and Pages use cases. Existing customer
  login app FLEXDRIVE 1321658899670696 remains unchanged; neither app is Ads Manager.
- ads_read/pages_read_engagement/pages_show_list are Ready for testing. Optional
  read_insights, instagram_basic and instagram_manage_insights not added yet.
  Instagram Facebook-login path supports insights; avoid bulk content/message grants.
- Prepared Employee system user name FlexDrive Analytics Reader, NOT created yet.
  Meta opened non-discrimination policy acceptance before creation. Await explicit
  approval for this policy and reporting-only asset access/persistent credentials.
  Existing Conversions API System User and tokens untouched. No connector code,
  credentials, billing, ads or deployment changes in this stage.

## Meta Dashboard Read-Only Audit - 2026-10-10

- User requested inspection before deciding on integration. Audited only FlexDrive
  portfolio 1761419678356905; Auto Mate is unrelated and must not be used.
- Facebook Page 1044408968766868 is portfolio-owned with Alexander full access.
  Instagram @flexdrive.ge (17841432881478668) is owned but shows Login needed;
  Alexander has partial access including Insights. User login is the next step.
- Portfolio Ad accounts shows No ad accounts added. Do not create one without
  agreeing account/currency/timezone settings. No ads/payment action authorized.
- FlexDrive Web Pixel 1020718363721235: Sep12-Oct9 overview shows PageView 92,
  ViewContent 13, browser Pixel only; cart/purchase delivery remains unverified.
  Diagnostics asks to allowlist flexdrive-front.vercel.app; no allowlist created.
  Conversions API connection pending; do not claim server delivery verified.
- FLEXDRIVE 1321658899670696 is an APP, not a second website Pixel. Unpublished,
  Facebook Login use case only. Add-use-case dialog offers app-install ads explicitly
  without Marketing API. Recommend a separate reporting app, subject to user decision.
- Existing Conversions API System User has Pixel/dataset assets only, no Page/IG/ad
  assets. No token generated/read, privileges changed or code written during audit.
  Business Domains list is empty; flexdrive.ge verification remains cutover work.
- Prior production GA4 env preparation was saved after user accepted possible
  restart; DigitalOcean confirmed config updated and deployment started (55fed051-
  9f59-411f-883f-5b5b3f2e4641). User explicitly stopped deployment monitoring and
  will check completion himself. No code push. Production env setup is now done.
  Credential appeared in a private tool response by mistake; user informed and
  explicitly declined rotation. Do not rotate or repeat requests about this.

## GA4 Local Credentials And Live Read Verified - 2026-10-10

- User approved the prepared reader JSON key creation; created exactly one active
  key for flexdrive-analytics-reader. Google confirmed file download. Initial
  browser download event timed out and local file was not found; do not create
  another key. User then confirmed Desktop location and explicitly requested
  local env configuration. Exact Desktop file found and parsed successfully.
- Configured ONLY BUSINESS_GA4_CREDENTIALS_JSON in local ignored .env from the
  complete JSON. Verified dotenv round-trip retains every field/private-key newline
  and all unrelated env values remain identical. No credential contents in logs,
  artifacts/docs or frontend. Desktop original left in place; no duplicate key file.
- Enabled Analytics Data API in existing flexdrive-494109, verified Status Enabled.
  Existing Viewer permission unchanged, no extra Cloud roles. Actual Google OAuth
  and both GA4 report batches succeeded using readonly scope and exact flexdrive.ge.
  October 1-10 period returned genuine empty data (traffic/search zero), Asia/Tbilisi.
- Live empty dimensionless GA report omitted metricHeaders/rows/rowCount. Fixed
  parser to accept that precise successful report kind/metadata/empty shape while
  still rejecting malformed/nonempty responses. 15 focused connector/scope tests
  pass, including this regression. No financial/other provider requests or DB edits.
- No prod env/config, push/deployment or storefront browser/server start. Local
  backend restart may be needed to pick up .env. Production still needs its own
  secret environment configuration and code deployment; launch event delivery/
  actual nonempty dashboard visual review remain pending.
- Proof: artifacts/analytics/ga4-data-api-enabled.png, ga4-reader-key-created.png
  and ga4-live-connection-verified.json (safe aggregate-only live verification).
  Supersedes prepared/unconfigured notes below. Browser chrome://downloads was
  blocked; no browser-policy bypass attempted. File was found after user direction.

## GA4 Dashboard Connector And Users UI Prepared - 2026-10-09

- User asked to continue GA4 dashboard connection now, before domain cutover;
  this supersedes older notes deferring connector implementation to the domain.
- Added read-only business/analytics.py and protected GET business/analytics/;
  fixed property 538949234 and exact flexdrive.ge on every request, excluding
  private business/admin paths. Separate batches for traffic and version-2 search.
  No financial/provider mutations; full-period users are not summed from days.
- Paired frontend /business/users now has real API states, period controls,
  modular ECharts chart/daily table, sources, result/no-result search words and
  deterministic Georgian summary. Tailwind/shared BaseButton; existing scrollbar
  styles retained. No fake values when credentials/API are missing.
- Existing google-auth/requests used with analytics.readonly scope, fixed reader
  identity/token endpoint, bounded timeouts. New FILE or JSON credential settings
  support backend-only secrets; neither configured. Existing Google OAuth unchanged.
  Server cache: 5-min fresh, <=24-hour last-good with stale timestamp, 60-sec failure
  backoff and concurrent request lock. Cache scope includes source/period/config.
- 59 business backend tests, 40 business frontend tests, typecheck, scoped ESLint,
  Django check and Nuxt production build passed. Google transport mocked; actual
  Google API compatibility/read, event delivery and dashboard visual review pending.
  No storefront browser or server start, database/demo changes, env edit, push/deploy.
- Reader key-create JSON dialog is prepared UNSUBMITTED in Chrome tab 1158491097,
  marked handoff. No key downloaded/created, Data API not enabled. Need action-time
  confirmation for one persistent reader key, backend-only local config and Data API
  activation. Proof: artifacts/analytics/ga4-reader-key-prepared.png.
- Stage 4 is still in progress until auth/live read and user review; ordered purchase
  funnel/events must not be claimed verified. See docs/BUSINESS_DASHBOARD_STAGE4.md.

## GA4 Reader Account And Viewer Access Created - 2026-10-09

- User confirmed the prepared action: create the technical account and grant
  Analytics viewing access. Created flexdrive-analytics-reader in Cloud project
  flexdrive-494109 with Create and close, skipping optional project/principal roles.
  Credentials table confirms the new account; existing sheets-reader unchanged.
- Added flexdrive-analytics-reader@flexdrive-494109.iam.gserviceaccount.com as
  Viewer on GA4 property 538949234 ONLY. Persisted property-access table has two
  rows: existing owner Administrator and new reader Viewer. Email notification off;
  no other Analytics roles, restrictions or account-level permission edits.
- No JSON key/secret created/downloaded, API enabled, env/config or backend/frontend
  connector changes, provider requests, deployment or push. Authentication to the
  server and report/API/UI implementation remain; this is not a live connection.
- Proof: artifacts/analytics/ga4-reader-account-created.png and
  ga4-reader-viewer-access-saved.png. Supersedes unsubmitted-form status below.

## GA4 Dashboard Access Preparation - 2026-10-09

- User now wants available GA4 dashboard connection prepared BEFORE domain cutover;
  exact flexdrive.ge reporting scope is retained, so pre-cutover reports may be empty.
- Read-only browser check found existing Cloud project FLEXDRIVE, flexdrive-494109.
  Enabled-API list has 25 services, no Google Analytics Data API. Credentials list
  contains only the existing sheets-reader service account; do not repurpose it.
- Prepared UNSUBMITTED create form for flexdrive-analytics-reader in this project.
  Proposed Analytics access is Viewer on property 538949234 only, no Cloud project
  roles or unrelated access. No service account/key/API enable/permission writes yet.
  Action-time confirmation required before creating persistent/security access.
- Chrome tab 1158491097 holds the filled create form, marked handoff. Screenshot
  artifacts/analytics/ga4-reader-account-prepared.png. No secret values inspected.
  Backend connector/API and frontend users report are not implemented yet.

## GA4 Event Retention Extended - 2026-10-09

- User explicitly requested GA4 event retention change from 2 to 14 months.
  Saved property 538949234 Event data = 14 months and reloaded the page to verify
  persistence. User data was already 14 months; reset-on-new-activity stays enabled.
  Google states retention changes take effect after 24 hours. No code/deploy needed.
- User deferred Google Ads setup because no Google advertising is running yet.
  Search Console is NOT connected; earlier search work was on-site search tracking,
  not Google organic search reporting. Search Console remains at domain cutover.
- Proof: artifacts/analytics/ga4-retention-14-months-saved.png. No account links,
  internal filter activation, provider requests, code/DB or deployment changes.

## Search GTM Published - 2026-10-09

- User explicitly overrode the GTM deferral and requested immediate publication.
  Published exactly the eight prepared search changes as GTM-MVNFL9TH version 10,
  GA4 search results and selection tracking. UI verified Version 10 is Live and
  Live, Latest at 23:06 Asia/Tbilisi. No other container changes included.
- Frontend push/deployment remains deferred to the user. New payload fields begin
  after deployment; end-to-end delivery/DebugView verification remains pending.
  Dashboard connector/domain cutover and internal filter Testing are unchanged.
- Supersedes unpublished-draft status below. See docs/SEARCH_ANALYTICS.md and
  artifacts/analytics/ga4-search-version-10-live.png. No code/DB/provider/deploy work.

## Search Analytics Prepared - 2026-10-09

- User authorized search analytics work after consent fixes; push and production
  deployment are explicitly deferred until all agreed work is finished.
- Paired frontend now emits search only from successful current catalog API count,
  with search_result_count, search_outcome, search_filtered and tracking version 2.
  Suggestion selection is separate select_search_result with public company SKU.
  No API/search ranking, database, schema, credentials or storefront UI changes.
- Shared in-memory query/revision state prevents pagination/sort/filter/category
  remount duplicates and stale A->B->A replies. SSR/setup waits for client mount.
  Invalid/failed results are not zero; denied searches are not replayed on consent.
  Full reload/reentry is a new results view, not session-wide unique-search counting.
- Analytics-only text normalizes whitespace, masks obvious email/Georgian mobile
  numbers and caps 100 characters. This does NOT sanitize query-bearing page_view
  URLs or automatic Enhanced Measurement events; their privacy audit remains.
- 48 focused frontend tests passed (11 search analytics, 16 HeaderSearch, 8 consent,
  13 business). Scoped lint, Nuxt typecheck and whitespace checks passed.
  No dev server or storefront browser test started; existing user servers retained.
- GTM-MVNFL9TH Default Workspace had zero changes before this work. Saved EIGHT
  unpublished changes: Search tag modification, five Version 2 data-layer variables,
  Search Selection tag and exact select_search_result trigger. No Submit/Publish.
- GA4 property 538949234 now has three Event dimensions search_outcome,
  search_filtered, search_tracking_version and one Standard metric search_result_count.
  Persisted table rows verified. Existing standard searchTerm is reused.
- Future report must filter eventName search + tracking version 2 + exact flexdrive.ge;
  never sum automatic view_search_results, suggestion selections or old search data.
  New fields/history cannot be claimed delivered until coordinated frontend/GTM
  release and DebugView verification. Dashboard connector remains deferred to domain
  cutover. No provider/order/payment requests, publish, deploy or push performed.
- Details docs/SEARCH_ANALYTICS.md; screenshots artifacts/analytics/ga4-search-*.png.

## GA4 Consent Dispatch Fixed Locally - 2026-10-09

- After inspection user explicitly authorized the proposed consent correction.
  Paired frontend google-tag-manager.client.ts now queues real Arguments objects
  for Google consent commands, matching Google's official gtag implementation.
  Consent defaults still precede GTM initialization; original combined choice,
  saved cookie semantics, and private business-route exclusion are preserved.
- Existing loaded Meta Pixel receives fbq consent revoke/grant on changes; GTM
  script onload also synchronizes it with the latest choice. No separate Meta
  script, pixel ID, consent split, GTM settings/publish, or credential edits.
- 8 new tests execute actual plugin/composable with Vue reactivity, covering
  denied default/refusal/no script, acceptance ordering and single GTM start,
  saved accept/reject reload, partial/invalid consent, revoke/reaccept to Google
  and existing Meta, late-load Meta synchronization, existing gtag and private
  routes. All 21 focused tests (including 13 business regressions) passed;
  scoped ESLint, frontend typecheck and whitespace checks passed.
- Browser used user-started https://localhost:3000. Tag Assistant live container
  showed recognised Consent Default/Update, granted tracking at container load,
  and the explicit denied update payload after revocation. Initial denied default
  verified too; after denial/reload no Google/Meta script elements were present.
  Local preferences/functionality/tracking restored to their original false values.
  Temporary debug session stopped; normal user servers left running.
- Evidence artifacts/analytics/ga4-consent-{granted,revoked,default-denied}-local.png.
  Meta command dispatch is unit-tested, not a full Meta network/delivery proof.
  Deployment and repeated production consent/vendor network verification remain;
  GA4's dashboard notification is not expected to change from local code alone.
  No backend/data/schema, order/payment/provider, deploy or push changes.

## GA4 Consent Audit - 2026-10-09

- User authorized inspection only before deciding on changes. Inspected the online
  DigitalOcean storefront and local frontend consent code. Existing UI preferences
  and functionality/tracking switches were all enabled; no consent Save submitted.
- Google Tag Assistant connected to the deployed site and debugged the existing
  live GTM-MVNFL9TH version. GA4 G-CKQC30CKYJ and Meta Base fired while opted in.
  Consent pane at Container loaded showed Consent not configured / Default consent
  state has not been set yet. Evidence: artifacts/analytics/ga4-consent-not-configured.png.
- Local google-tag-manager.client.ts gtag shim pushes a rest-parameter Array;
  Google's official consent setup uses dataLayer.push(arguments). This mismatch
  is the leading explanation, not proof every deployed consent failure has one cause.
  Initial refusal and later revocation remain unverified; UI toggle actions timed
  out and no changed choice was saved. Do not claim full consent lifecycle verified.
- Frontend AGENTS explicitly keeps analytics/marketing combined. Preserve that
  decision unless user asks to split. Proposed next step is narrowly correcting
  consent message dispatch, then checking accept/refuse/revoke and Meta handling.
  This was an inspection-only checkpoint; subsequent user authorization and local
  implementation are recorded in the section above.
- Temporary Tag Assistant session stopped; no domains left actively debugging.
  No app code, GTM publish/settings, GA4 configuration, env, DB, provider or deploy
  changes. Browser checks generated ordinary page/debug analytics only, no orders.

## GA4 Internal Traffic Rule Saved - 2026-10-09

- User confirmed a fixed home public IP and supplied it specifically for GA4
  internal-traffic configuration. The stream previously had no internal IP rules.
  Saved ONE rule named FlexDrive — სახლის ინტერნეტი with IP address equals the
  user-supplied address and traffic_type internal. Reopened and verified persistence.
- Existing property Internal Traffic filter is Exclude, traffic_type exactly
  internal, and remains Testing. No activation or permanent exclusion performed.
  Real home-network visit recognition and Test data filter name reporting still
  require verification before activating. Do not claim the visit test has passed.
- Evidence: artifacts/analytics/ga4-internal-ip-rule-saved.png and
  artifacts/analytics/ga4-internal-filter-testing.png. No app code, provider flow,
  credentials, database, deployment or other analytics setting changed.

## GA4 Reporting Domain Decision - 2026-10-09

- Latest user instruction: defer activation and live verification of the prepared
  flexdrive.ge GA4 scope and www redirect until the flexdrive.ge domain cutover.
  At that checkpoint bind DNS/TLS/hosting, deploy/verify the redirect, set canonical
  siteUrl, and connect/verify read-only GA4 reporting with the exact domain scope.
  Do not treat prepared code as an already active live integration.
- User explicitly chose ONLY flexdrive.ge for dashboard GA4 reporting, excluding
  old DigitalOcean/Vercel/localhost history. Reuse property 538949234, stream
  G-CKQC30CKYJ and GTM-MVNFL9TH. Browser read-only audit confirmed those IDs.
- business/ga4.py prepares runReport bodies with hostName EXACT flexdrive.ge;
  additional filters use AND so they cannot widen the source. This is preparation
  only: no Google credentials, live API requests, new business API route or UI
  connection yet. Future connector must use this scope and include it in caching.
- Paired frontend server middleware prepares a 308 www.flexdrive.ge -> HTTPS
  flexdrive.ge redirect for GET/HEAD, preserving path/query. Main/local/preview
  hosts, forwarded-host headers and POST callbacks do not trigger it.
- 2 backend scope tests, 3 frontend redirect tests, scoped ESLint and frontend
  typecheck passed. No servers, browser tests, DNS/TLS/hosting or deploy changes.
  Domain binding/restricted-access verification remains in the agreed cutover.
- GA4 domain filter does NOT remove test orders from DB financial reports.
  Actual launch/report start date is undecided; do not guess it or delete history.
- Audit findings remain separately pending: mixed source hosts, empty unwanted
  referrals (subsequently fixed below), internal filter Testing, consent
  signals inactive, add_to_cart/purchase delivery unverified in last 28 days,
  missing search-result count tracking. Do not resolve other issues automatically.

## GA4 Bank Referral Exclusion Saved - 2026-10-09

- User explicitly authorized this browser configuration change. In the existing
  G-CKQC30CKYJ stream's Google tag, saved List unwanted referrals with ONE condition:
  Referral domain exactly matches payment.bog.ge. Observed Configuration saved
  and reopened the panel to verify the persisted exact-match value.
- Screenshot: artifacts/analytics/ga4-bog-referral-saved.png. No other analytics
  setting, consent policy, GTM workspace publish, app code, payment/provider flow
  or deployment changed. This verifies configuration persistence, not a new
  end-to-end bank-return attribution test. Existing historical attribution is
  not rewritten automatically. Other audit findings remain pending separately.

## Business Dashboard Operations - 2026-10-09

- User authorized stage 3 after reviewing sales/finance. Protected GET-only
  business operations API and paired frontend `/business/operations` are implemented.
  Current snapshot: physical returns, owned receipt-lot balances/age/history cost,
  saved payment attempts/issues and latest stored Cross Motors/EasyWay results.
- Independent 20-row pages and return/payment filters; full matching totals.
  Restored allocations do not consume stock. Unknown costs remain unknown;
  negative lot balances are flagged. Private supplier IDs/PII/provider JSON and
  raw errors are excluded. Missing sync history is not proof of failed scheduling;
  EasyWay omits unchanged successful checks. No live bank/provider checks or actions.
- 44 focused backend tests pass on disposable SQLite; 33 frontend tests, scoped
  ESLint/typecheck/template compilation pass. Compiled CSS includes all 110 static
  operations utilities; 17 public manifest roots do not statically import its API
  code. Local frontend build passed; the next checkpoint is user browser review.
- No real business-data/schema/env/credential, provider, remote DB, deployment or
  push changes. No browser/dev server started; user reviews each completed stage.
  Do not begin stage 4 automatically. Do not create branch/worktree.
- User deferred combining delivery/buffer profit and full/net business profit until
  discussion with their accountant and agreement on calculations. Preserve existing
  separate financial figures. See docs/BUSINESS_DASHBOARD_STAGE3.md and the plan.
- During review user explicitly requested reusable `BaseSelect` for dashboard
  dropdowns. Both operations filters now use it; retain this shared component pattern.
  Short payment labels have explanatory hints; ordinary paid transactions remain
  in sales/finance, while stored review issues can include paid transactions.

## Production Returns Migrations - 2026-10-08

- User confirmed code pushed and explicitly authorized migration-only production
  rollout using the supplied DigitalOcean database. Pending plan contained only
  catalog.0027 and commerce.0035/0036; pricing dependencies were already applied.
- Applied these three migrations in one committed PostgreSQL transaction with
  bounded lock/statement timeouts and exact target/dependency guards. Verified
  owned-stock field, all five return/inventory tables and required admin permissions.
  All-app migration plan is now empty.
- No demo orders/data, bank/supplier/carrier requests, credential/config edits or
  deployed-browser checks. Production schema is ready; this is not a claim of
  real bank refund verification. Staging had already applied these migrations.

## Staging Returns Schema Verified - 2026-10-08

- After user-confirmed push, connected only to the explicitly supplied Neon staging
  database. Both return-target and all-app migration plans were already empty.
  Confirmed catalog.0027 and commerce.0035/0036 applied; no migration rerun needed.
- Read queries succeeded for owned balance and all five return/inventory tables;
  required return view/change and owned-stock view permissions exist.
- No database writes, demo orders, bank/carrier/supplier calls or production access.
  User requests migration-only rollout, without creating remote test data.

## Offline Returns Walkthrough - 2026-10-08

- User explicitly forbids real bank/supplier/carrier requests during walkthrough.
  Ordinary admin refund buttons remain real: never use them for this demo.
- Standalone scripts/returns_preview.py creates a fresh temporary SQLite DB,
  three synthetic BOG-shaped orders (TEST-01/02/03), and a disposable auto-login
  superuser. Binds only 127.0.0.1:8011, with an unmistakable Georgian yellow banner.
  No existing database/env/credentials changed. Do not expose/proxy this server.
- In the preview process only, BOG transport is simulated; status check completes
  the fake refund. Outbound socket connections/DNS blocked before Django startup;
  email/caches/storage local, browser external subresources blocked by CSP.
- --check passed all three complete admin flows, stock/payment finalization and
  outbound socket/DNS denial checks. The server uses a separate fresh DB, leaving
  its three demo orders untouched for user review. Browser review remains pending.
- See docs/RETURNS_OFFLINE_PREVIEW.md. Stop the preview process after review;
  normal user-started servers must remain running.

## Return And Inventory Admin Lists - 2026-10-07

- Registered read-only OrderReturn (დასაბრუნებელი ნივთები) and OwnedStockLot
  (FlexDrive-ის მარაგი). No schema change or manual stock editing. Return lines
  remain inline-only. Order actions remain the only receipt/refund mutation path.
- Return list defaults to awaiting; received/all-history filters preserve history.
  Shows products/quantities, linked order details, receipt and separate payment
  state. Details link to the existing permission-checked receipt action and order.
- Stock list defaults to positive remaining lots, with empty/all history filters,
  received and remaining quantities, company code and source-order link. Balance
  subtracts non-restored sale allocations; each row is a receipt batch, explicitly
  explained in Georgian. Search supports product, company SKU and source order.
- View permissions enforced, accountants stay report-only. History cannot be
  added/edited/deleted in these admin sections. Existing foundation admin test
  updated to reflect read-only registration instead of inactive models.
- SQLite checks: 20 foundation/customer-return tests passed; 3 new list tests
  passed after correcting test expectations for Georgian label capitalization
  and switching the accountant fixture to an ordinary viewer for access checks.
- User explicitly deferred BROWSER verification: do not start a server or open
  browser for this stage. User will start backend and open admin in Chrome first;
  then jointly review the three agreed scenarios. No real provider/remote work.

## Dispatched Return Actions - 2026-10-07

- Order admin now exposes Georgian return start for paid shipped/delivered orders,
  then receipt/inspection while awaiting goods. Start records intent only; GET
  and invalid submissions do not mutate stock/payments. Order-change permission
  is enforced on all action endpoints.
- Full receipt requires saleable + unsaleable counts equal every expected line.
  Only saleable units credit owned inventory. Identical receipt retries are safe.
  Refund becomes available only after receipt; the server enforces this on direct
  requests too. Receipt does not itself send a bank request.
- Customer-return refund form omits supplier-procurement questions. Dedicated
  bank finalization cancels the order without crediting stock a second time or
  restoring purchased supplier inventory. Existing pre-dispatch paths preserved.
- 23 focused SQLite tests pass (4 new dispatched-flow tests plus 19 previous
  refund tests), including real admin routes with mocked bank, invalid receipt,
  permissions, unreceived refund denial and repeated receipt/bank completion.
- No migration, business-data edit, real provider request or remote change.
  Next: operational waiting/owned-stock lists and integrated browser review.
  Return cancellation/restart is not implemented; rollout checks remain separate.

## Pre-Dispatch Return UI And Refund Integration - 2026-10-07

- User clarified Georgian text applies ONLY to this return workflow, not the
  entire admin. User wants focused implementation/checks, no legacy fixture audit.
- Order refund button now opens a Georgian confirmation page: whole-order
  procurement choice (no initial selection), product quantities, full amount,
  consequences and required non-dispatch confirmation. All-owned orders hide
  the unpurchased choice. Existing choice stays locked across retries.
- Admin refund preparation atomically records the case/physical on-hand receipt
  before requesting BOG. Unpurchased releases source stock only on confirmed
  refund; on-hand credits owned stock immediately and finalization does NOT
  credit it again or release purchased supplier holds. Bank timeout/rejection
  retains receipt history. Repeated requests reuse the existing bank action/key.
- Linked payment-admin refund route redirects to order confirmation; no bypass.
  Dispatched returns remain blocked pending the next receipt workflow stage.
  Return cases freeze manual fulfilment, new EasyWay submission and tracking
  advancement even if bank rejection restores payment status to paid.
- Order return banners and bank-status check labels/messages are Georgian.
  No schema, business-data, provider or remote changes in this stage.
- 19 focused refund tests passed (7 new); existing UI assertions updated to the
  intended Georgian form/required choice. Next: dispatched return start/receipt,
  then operational waiting/owned inventory lists. No full-admin translation.

## Returns Inventory Selling Stage - 2026-10-07

- User clarified ALL existing orders are test orders. Site is deployed but not
  publicly launched/on its own domain. Do not add elaborate historical-order
  compatibility solely for them; no data reset requested or performed.
- Own-stock allocation implemented in cart, buy-now and verified BOG finalization.
  Product.owned_stock_qty is separate from external stock_qty; one owned unit is
  sellable without the external five-unit reserve. Public API shapes unchanged.
- OrderItemInventory stores external quantity/source and exact allocated cost;
  OwnedStockAllocation consumes FIFO receipt lots. Combined checkout reservations
  reserve quantity, not specific lots; actual source/cost fixed at finalization.
  Owned-only sales create no supplier hold. Pre-dispatch cancellation restores
  the same sources once. Receipt-driven cases cannot use old refund/restore routes
  until the next dedicated finalizer stage. New operational UI remains disabled.
- Supplier regular/bulk sync preserves owned stock; missing-feed handling zeros
  external stock and retains owned products. Only supplier-auto-archived products
  can reopen on receipt/restoration; manual visibility choices are retained.
- Accounting uses exact total allocated cost; original supplier snapshots stay
  unchanged, unknown costs remain NULL, resale receipts retain lot provenance.
- Applied catalog.0027 + commerce.0035/0036 LOCAL SQLite only, with ignored backup
  local-docs/returns-stage3-backup-7r5l_yzn/db.sqlite3. Old columns across 33 existing
  catalog/commerce/accounts tables verified unchanged by hashes; target plan empty.
- Tests: 77 foundation/refund/hold/accounting passed; final inventory/callback/hold
  suite 79 passed, 1 PostgreSQL concurrency skipped; search/accounting UI/export/
  migration suite 87 passed. Broader old SKU-fixture and category-price failures
  reproduced on unmodified HEAD. PostgreSQL runtime/browser checks remain.
- No remote mutations, real bank/supplier calls, push or deployment. Next is stage
  4 pre-dispatch Georgian refund choice + source-aware bank finalization, followed
  by dispatched receipt workflow and operational lists. See the detailed plan.

## Returns And Owned Inventory Foundation - 2026-10-07

- User approved staged implementation of full-order returns and FlexDrive-owned
  stock, with Georgian admin UI. Procurement selection is ONCE per order.
  Unpurchased cancellation releases supplier reservation; bought/on-hand goods
  go directly into owned inventory; dispatched goods require receipt/inspection
  before any refund request. Do not enable incomplete flows between stages.
- First checkpoint implemented only inactive foundation: OrderReturn,
  OrderReturnLine, immutable OwnedStockLot and internal commerce/returns.py receipt
  services. No admin registration/routes, bank/carrier integration or changes to
  checkout, stock availability, supplier holds/sync or existing refund behavior.
- commerce.0035 adds only new tables/constraints; created and tested, NOT applied
  to local business DB, staging or production. No legacy procurement backfill.
- 16 new foundation + 24 existing refund/supplier-hold tests pass on disposable
  SQLite. Migration drift and whitespace checks pass. PostgreSQL/browser pending.
- Next is source-aware inventory selling (all checkout/callback paths), then
  refund integration, returns UI and end-to-end checks. Lots are not yet available
  to customers. Preserve original historical costs, supplier safety reserve/hold
  behavior and intentional catalog publication controls when integrating.
- Detailed stages and invariants: docs/RETURNS_IMPLEMENTATION_PLAN.md.

## Catalog Search Year And Local Browser Verification - 2026-10-07

- Free-text search now extracts a single unambiguous standalone year (1900-2100)
  after resolving a vehicle and checks the inclusive ProductFitment year range.
  Model numbers such as Peugeot 2008 and standalone numeric IDs remain searchable.
  Engine and year must match the same fitment; universal products retain their
  existing behavior. Description/title year mentions cannot bypass compatibility.
  Explicit API filters still constrain search. No migration or product edit.
- Georgian model spellings with a trailing ი (ფორესტერი) also resolve to their
  Latin model names. Other product-word matching is unchanged in this follow-up.
- Deployed mobile close/reopen worked when checked; the earlier reported bug was
  in the unshipped local stale-response changes. Added explicit reload on mobile
  open plus three tests, preventing that regression when the changes are deployed.
- 62 backend search/cache/internal-SKU tests and 15 frontend tests pass; frontend
  typecheck passes. Search stock fixtures now exceed the five-unit reserve so
  ranking/stock-filter tests actually exercise customer-available stock.
- Extended audit uses every fitment and adds start/end-year name combinations:
  2,037 products, 25,091 membership checks / 16,316 distinct queries, zero failures
  and no length skips. Separate read-only comparison of 216 vehicle/year queries
  against saved fitments found no missing or extra products.
- Browser verified user-started https://localhost:3000: no-year Forester cover
  search 4 results, 2019 gives 2, full LH name gives 1 in dropdown and catalog;
  2018 gives 2 covers for 2012-2018, 2020 gives none. Original full LH name gives 5.
  Mobile 375px reopen/route-query loading, rapid input replacement, reordered Latin
  spelling, compact company SKU and clear-search behavior verified. Viewport reset.
  Temporary agent-started servers were stopped; user-started servers left running.
  Production was not changed; push/deploy and PostgreSQL runtime verification remain.

## Catalog Search Full Audit - 2026-10-07

- Supersedes the narrower same-day fragment fix below. Search now requires all
  meaningful words in any order, normalizes whitespace/punctuation/pasted invisible
  characters and Georgian uppercase, and uses bounded per-word Latin patterns.
- Whole-word side/placement aliases support legacy names without matching LH inside
  unrelated words. Numeric name terms remain distinct; identifier prefixes work.
  Shared/prefix vehicle matches retain all candidates and scope models to the make.
  Literal name/identifier matches survive accidental vehicle interpretation;
  explicit catalog filters and supplier-SKU privacy remain intact.
- Exact code/name results precede partial matches/stock preference during search.
  Standard FD codes support compact/spaced spelling; max query length is 255 to
  accommodate Product.name. Default listing stock order is preserved.
- Paired frontend HeaderSearch invalidates stale/debounced requests immediately on
  input change/clear/close/unmount. 12 actual-Vue search tests and typecheck pass.
- Read-only SQLite-only `audit_catalog_search --fail-on-missing --output <json>`
  checks every public product's names/variants, vehicle combinations and public IDs.
  Final local sweep: 2,037 products, 20,280 membership checks / 12,117 distinct
  queries, zero failures and no length skips. Initial broad sweep had 2,183 missing
  memberships (including 47 full-name checks); these are cases, not distinct bugs.
  54 backend search/cache/internal-SKU tests pass. See docs/CATALOG_SEARCH.md.
  No catalog/schema or remote changes. Both deployments and deployed-site/
  PostgreSQL verification remain pending; no browser/server session was started.

## Catalog Full-Name Search Fix - 2026-10-07

- Reproduced zero results for `სარკის ქვედა ხუფი (LH)` locally: parsing removed
  the middle placement word and incorrectly searched the adjacent phrase `სარკის ხუფი`.
- Search now requires all original product phrase fragments around extracted
  vehicle/attribute terms, preserving adjacency within each fragment. Normalize
  bracketed attribute tokens and ignore standalone copied-name separators.
- Dropdown and catalog APIs now return 5 matching LH covers locally; RH isolation
  and the supplied rear-bumper example verified. 28 search/cache/internal-SKU tests pass.
  No data/schema/frontend or remote changes; production deployment remains pending.

## Accounting Production Migrations - 2026-10-04

- After user-confirmed production code deployment, applied only commerce 0033
  (historical purchase-cost fields) and 0034 (accounting report permission) to the
  explicitly supplied production database, in one transaction. Catalog pricing
  dependencies were already applied; no pricing reset performed.
- Verified the target migration plan is empty, new fields query successfully and
  view_accounting_report permission exists. Existing product/category/order/item/
  payment/user column values verified unchanged using pre/post row hashes.
- No demo data or accountant account created; their creation remains deferred.
  Deployed production browser verification was not performed.

## Accounting Buyer Details And Optional Purchase Columns - 2026-09-30

- Order headings show saved buyer_type and, for legal entities, saved
  company_is_vat_registered (yes/no; null remains explicitly unspecified).
  XLSX includes both buyer columns for sales and refunds; no checkout changes.
- `show_purchase` checkbox defaults off, hides gross purchase unit/total columns
  including order/period totals. Net cost and product profit remain visible.
  Checkbox submits the GET form; pagination/export URLs retain the selection.
  XLSX omits hidden columns entirely using the same column selection helper.
- 53 existing access/UI/export tests plus 2 new visibility/buyer parity tests passed.
  No migration or remote changes in this stage; browser visual review remains.

## Accounting Staging Preparation - 2026-09-29

- User authorized staging accountant access and demo data. Commerce 0034 and its
  dependencies were already applied (migration plan empty); no migration run needed.
- Created staging `accountant` in `FlexDrive Accountants`, active staff/non-superuser,
  with only `commerce.view_accounting_report`. Password supplied in session only.
- Seeded 36 marked orders, 72 distinct product lines, 42 mock payment/refund events,
  April-September 2026. Existing catalog products/categories and pre-existing
  orders/items/payments verified unchanged by row hashes in the same transaction.
- Local code against staging DB verified accountant login, redirect, report and
  XLSX. Deployed-site browser verification remains outstanding. Production untouched.
- `accounting_demo --staging` permits only the exact approved Neon staging host
  and neondb database. Default stays SQLite-only; all other remote targets denied.
  `--staging --delete` retains existing marker/link safety checks. Three demo
  creation/cleanup/remote-guard tests pass. Push this command/test change as well.

## Accountant Access - 2026-09-29

- User explicitly authorized the previously deferred accountant account stage.
- Local SQLite account `accountant` belongs to `FlexDrive Accountants`, with only
  `commerce.view_accounting_report`; active staff, never superuser. Credentials
  were provided privately in conversation and must not be recorded in files.
- Login redirects to the accounting report. Filters/export and own password change
  are allowed; other admin routes are denied, with sidebar/site links hidden.
- Migration commerce.0034 applied locally only. No staging/production account or
  deployment performed. 51 access/export tests passed; actual local account login,
  redirect, report, XLSX and forbidden product/user pages verified with Django Client.

## Accounting Excel Readability

- Export now starts with FlexDrive report title, exact period, selected status,
  order count and name/SKU filter; includes GEL/VAT/timezone and relevant date/sign
  semantics. Table header is row 7; data begins row 8. Flat spreadsheet retained.
- Alternating pale bands follow complete financial-event groups, not individual
  product rows. Dark title/header/total, wrapped labels, tuned column widths,
  numeric 2-decimal money with red parenthesized negatives. Freeze first 7 rows
  and 4 identity columns. AutoFilter excludes the static report total.
- Landscape A3 print setup fits width, repeats title/header rows, adds page numbers.
  No dependency, calculation, data or permission change. 32 focused export/UI/demo
  tests passed, including metadata, banding, frozen panes, numeric/sign safety,
  correct totals and filters. Actual desktop Excel rendering not checked.

## Accounting Order Blocks - Latest UI

- User found repeated order numbers confusing. UI now uses a bordered block per
  financial event: one order heading/date/status, product count and unit count,
  product-only table, subtotal, then delivery/buffer/full order amount once below.
- Paginate 20 complete event blocks, never split an order's products across pages.
  All-mode original receipt/refund remain separate dated/status-labeled blocks;
  grouping uses transaction IDs, not display text. Period totals cover all pages.
  SKU search still product-only and hides order fee footer. XLSX remains flat for
  spreadsheet filtering with identical underlying rows and totals.
- 30 UI/export/demo tests passed, including order-boundary pagination. Browser
  verified 3 products/4 units in one block, one order heading, 795 GEL total,
  desktop fit and mobile overflow containment. No real data/schema/remote changes.

## Accounting Product Name Search

- Existing SKU input now labeled product name or SKU; substring search includes
  saved product_name as well as both SKUs in DB and line filtering. Same export
  filters and product-only totals. Two focused name/export/SKU tests passed.
- Verified local two-item example: FD-DEMO-202609-32, paid September 6 2026,
  DEMO-FD-32-1 mirror 110 GEL and DEMO-FD-32-2 brake pad 170 GEL; full order 301 GEL.
  Select Sept 6 start/end, paid, blank search to see both rows and shipping together.

## Accounting Markup Percentage Removed - Latest Decision

- User removed the markup-percent column again. Ledger UI and XLSX retain product
  profit excluding VAT (before other expenses), but no percent column or explanation.
  This does not change catalogue markup pricing or internal calculation precision.
- Multi-item orders remain adjacent product rows sharing order number. Delivery,
  buffer and full order amount appear only on the first row. Existing filters and
  72-line demo dataset unchanged. 26 accounting UI/export/demo tests passed.

## Accounting Filters And Expanded Demo - Latest Decision

- Restored day/month ranges and direct SKU substring search (company or supplier
  SKU, case-insensitive). SKU selects only matching product lines, not sibling
  products. In SKU mode order-level shipping/buffer/full payment columns and totals
  stay blank: these cannot be attributed to one product without invented allocation.
- Added "all": confirmed original receipts plus confirmed refunds by event date;
  refunds negate quantities and line/order totals, preserving positive unit prices
  and markup %. Net totals subtract refunds exactly once. Paid-only still excludes
  any order with completed refunds. Refunded-only displays positive reversals.
- Added markup-percent column (15 -> 35 gives 133.33%); existing product profit is
  VAT-exclusive markup before other expenses (16.95), not net company profit.
  Percent is not summed. Excel shares all filters, signs and numeric cells.
- Local demo refreshed atomically: 36 orders, 72 distinct product SKUs/lines,
  42 mock transactions across April–September 2026, 1/2/3 lines per order and varied
  quantities/prices. 6 refunded orders; paid-only shows 30 orders/54 lines. All view
  has 90 event lines and net 10888 GEL; refunded-only 2183 GEL. Unrelated order,
  item and transaction values verified unchanged. No stock/providers/users affected.
- 25 UI/export/demo tests passed, then two focused export-filter/demo tests passed
  after adding exact signed XLSX/markup/SKU assertions. No schema/remote changes.
- Isolated browser QA confirmed day/month visibility, all-status signed totals,
  unchanged totals across pages and exact SKU-only rows. Preview server removed.

## Single Accounting Ledger - Latest User Decision

- Replaced all accounting tabs with ONE product table, start/end dates and only
  successful/refunded status filter. Fixed 18% VAT; one-sheet XLSX matches table
  and includes full-period totals at bottom. No search/month-mode/tax selector.
- Successful uses confirmed payment date and excludes any order with a completed
  refund, including refunds outside selected period. Returned uses refund date.
  Unpaid/orphan orders are absent. GEL ledger only. Delivery/buffer and full payment
  amount appear on first product row only; quantity/cost/sales/profit totals cover
  all pages. Purchase cost is not evidence of supplier cash settlement.
- commerce/accounting_ledger.py reuses validated saved order/payment facts. Partial
  or ambiguous refund allocations do not invent product-cost/profit reversals.
  Internal arithmetic safeguards remain, with no accountant review UI.
- 43 focused tests passed; isolated browser QA confirmed one table/no tabs,
  successful/refund filters, totals and XLSX download. Temporary preview removed.
- Local marked demo batch safely recreated with ALL purchase costs populated;
  unrelated orders verified unchanged. July–September successful: 5 orders,
  6 items, gross 286, purchase gross 90, product profit 101.70 GEL. Returned:
  1 order / 2 items, gross 93, purchase gross 30, profit reversal 33.90 GEL.
- No new schema, remote changes, or accountant account. User review remains next.

## Accountant Review Section Removed - Latest Decision

- User removed the accountant-facing exceptions/review concept entirely. No review
  tab, undated global query/count, issue-note columns, unallocated/unknown-cost alerts
  or review worksheet in XLSX. Four remaining sections/sheets: summary, orders,
  products, payments/refunds. Preserve internal arithmetic/allocation validation;
  do not invent missing amounts or change operational payment recovery behavior.
- Orders are one row per order; products are one row per order item; cash is one
  row per confirmed payment/refund event. User requested explanation of overlap,
  not authorization yet to merge these three remaining sections.

## Accounting Simplification - Latest User Decision

- User confirms FlexDrive is a VAT payer and explicitly requires fixed 18% in
  accounting from the start. Removed unknown/scenario selector; stale tax_mode URL
  parameters are ignored. UI and XLSX always use 18% for purchase/sale calculations.
- Accountant sees only orders/items backed by confirmed captured sale/capture or
  confirmed refund records. Pending/failed/authorization-only orders are excluded,
  including the pending demo order (retained in DB, hidden from accounting).
- Remove fulfilment states from accounting; show only paid/refunded derived from
  confirmed events, not mutable delivery/payment workflow flags. Products also
  identify paid/refunded. Normal operational order admin is unchanged.
- Main summary displays confirmed cash totals and known product markup less
  confirmed refund markup. Removed duplicate order-created summary cards from UI.
  No new migrations, account permissions or remote deployment. 41 focused tests pass.
- This overrides earlier notes requiring unknown VAT/scenario UI and showing all
  order statuses. Dedicated accountant account is still deferred for user review.

## Domain Cutover Decision - 2026-09-28

- 2026-10-09 follow-up: activate and verify prepared www.flexdrive.ge ->
  https://flexdrive.ge redirect and flexdrive.ge-only dashboard GA4 reporting
  at this cutover, including the required read-only reporting connection.
- User deferred BOG reconciliation scheduler setup until migration to flexdrive.ge; do not provision it before that stage.
- flexdrive.ge must initially remain restricted to authorized testers, not publicly open. Establish and verify access protection before exposing the domain; noindex alone is not access control. Account for direct hosting URLs and required bank/provider callbacks without exposing the storefront.
- After restricted domain cutover, update domain-dependent configuration/URLs (frontend/backend origins, OAuth redirects, reCAPTCHA, email links, bank redirects/callback where applicable), configure payment reconciliation scheduler, and complete deferred integration/analytics checks before public launch.
- Cross Motors category-warning investigation confirmed existing category assignments are preserved; new supplier products are created Draft in category "ახალი" for manual categorization. Warning text is misleading, not evidence of category reassignment. No importer code or data changed during review.

## Production Progress Confirmed by User - 2026-09-28

- Live browser audit on 2026-09-28: backend app has only two Job components, crossmotors-sync and easyway-tracking; no BOG reconciliation job in this app or its displayed job history. An external scheduler was not checked.
- Both triggers are `0 0 * * *` in Asia/Tbilisi, while wrappers calculate UTC dates. This differs from documented UTC trigger: EasyWay first due execution is October 3 at local midnight, rather than October 2 UTC. Normalize timezone before relying on documented due dates.
- Latest Cross Motors scheduled run succeeded September 28 local time: 2030 updated, 0 created, 0 archived; category inference warnings remain in log for separate review.
- Latest EasyWay run succeeded by skipping under the ten-day wrapper; actual Django tracking command/provider/DB access is not proved by that skip. Neither job has component alert policies; app alerts shown were Failed Deployment and Failed Domain Configuration only.
- Audit was read-only: no job created, triggered, or schedule changed.

- User confirms contact and receipt environment variables were added last week.
- User observed successful Cross Motors sync reports in production admin; sync runs successfully at the longer pre-launch interval. Reduce cadence at launch as planned.
- User has not created orders/payments for current verification. No EasyWay report is expected for empty/skipped/unchanged successful scheduled runs.
- User recalls enabling payment reconciliation cron, but current live scheduler configuration and execution have not been verified. Do not state it is disabled solely from older preparation documents. Payment reconciliation stores per-payment issue/attempt fields and optional problem emails, not a batch report for every execution.
- Older handoff/deployment documents contain historical setup status; reconcile with these confirmations and live evidence before proposing repeated setup.

## Production Analytics Follow-up - 2026-09-24

- Existing GTM container GTM-MVNFL9TH and GA4 stream G-CKQC30CKYJ are reused for production; no separate property/container is required by the current plan.
- Production frontend GTM ID was corrected and deployed. Browser confirmed GTM, GA4 and Meta Pixel script loading, not end-to-end event delivery.
- User explicitly deferred full analytics verification until migration to flexdrive.ge and completion of site flows. Revisit page views/search/product/cart/checkout events, paid purchase values/company SKUs and browser/server deduplication then.
- Cookie consent handling/revocation remains outstanding; do not treat script loading as completion of analytics readiness.
- Cash-on-delivery is disabled by product decision and excluded from this verification scope.

## FlexDrive Internal SKUs - 2026-09-23

- Existing `Product.sku` remains PRIVATE supplier/legacy identity for imports,
  comparisons, supplier API and image transfer. Public product/cart/buy-now `sku`
  and `display_sku` expose ONLY `internal_sku`, with no supplier fallback. Public
  search no longer matches supplier SKU. Admin shows/searches both codes.
- Browser analytics and server Meta purchase IDs use company SKU. New BOG basket
  IDs also use company SKU; private payment/order snapshots preserve both codes.
- Root category groups 01–08 match the supplied workbook. Children inherit root
  group. `SkuSequence` retains high-water marks; admin save with a mapped category
  assigns `FD-XX-NNNN` atomically. Imports never allocate. Company code is readonly
  in admin and survives category changes/stale saves. Deleted numbers are not reused.
  Publishing without a company SKU is blocked in form, bulk action and database.
- Public slugs/canonicals/sitemap use FD codes. Stored slugs stay unchanged and old
  links still resolve. Do not expose the stored supplier-bearing slug publicly.
- Local migrations `catalog.0022`–`0024` and `commerce.0032` applied; 2,037 pairs from
  `FlexDrive_Prices_Paired_Updated.xlsx` imported locally, all matching, no conflicts.
  Existing values across all 26 catalog/commerce tables verified unchanged.
  Staging subsequently prepared with catalog.0022–0024 and commerce.0032, all
  2,037 workbook mappings imported. Existing staging test1234 assigned FD-01-0216
  from its lighting category; group 01 counter is now 216. Other existing product,
  category and order values verified unchanged by hashes in one transaction.
  Staging commerce_orderitem.internal_sku has SQL DEFAULT '' for old deployed
  checkout compatibility until code deployment. No code push/deploy performed by
  the agent. Unrelated pending pages migration was not applied.
- Production subsequently prepared: catalog.0022–0024 and commerce.0031–0032 applied
  atomically; all 2,030 existing products received their exact workbook codes.
  Seven workbook products absent from production were not created: CM-000537,
  CM-000860, CM-000974, CM-000975, CM-001065, CM-001155, CM-001156. Counters use the
  full workbook maxima, protecting these numbers from reuse. On return, assign their
  reviewed original mapping explicitly. Old product/category/order/order-item values
  verified unchanged by hashes. Production SQL defaults '' on orderitem.internal_sku
  and paymenttransaction.reconciliation_issue preserve old deployed insert behavior.
  No cron, bank/email call, or code deployment performed. Backend then frontend
  deployment and browser verification remain outstanding.
- `import_internal_skus --input <xlsx>` is dry-run by default; `--commit` fills
  unassigned codes atomically. It refuses duplicates, missing products, collisions
  and replacement of existing assignments. Only SKU columns are read for import.
  Supplier refreshes preserve assigned codes. Import also advances group counters.
- New COD/card orders snapshot both codes. Old orders/receipts and pre-migration
  payment snapshots retain original identifiers; no historical backfill. Admin
  supports both codes. See `docs/INTERNAL_SKUS.md` for rollout and verification.
- Latest verification: 153 focused tests passed, then 11 allocation/URL tests passed
  after extra sitemap/group coverage; PostgreSQL concurrency test skipped on SQLite.
  Frontend typecheck passed. Broader legacy tests have stock,
  delivery and catalog expectation failures; representative failures reproduced on
  unmodified HEAD; old Published-product fixtures now also need company codes.
  Browser and production PostgreSQL verification remain pending.
- On remote rollout apply catalog 0023 and commerce 0032, import reviewed SKU mapping,
  then catalog 0024. The latter refuses Published products without company codes.

## Payment Reconciliation Preparation - 2026-09-23

- User authorized preparing monitoring now; cron activation remains deferred.
  `reconcile_bog_payments` checks stale/unresolved BOG SALE transactions through
  the existing verified finalizer. It never initiates a charge or refund.
- Migration `commerce.0031_payment_reconciliation_monitoring` adds operational
  lease/attempt/issue/notification fields. Deploy migrations before command/admin use.
  Applied locally; 90 targeted monitoring/callback/payment/refund tests passed
  (including the added lease-expiry case). Migration 0031 also confirmed on staging
  and applied on production during SKU preparation; scheduler remains disabled.
- Empty/dry-run batches make no bank requests or send emails. Paid-without-order
  and missing-bank-ID cases require admin review, not blind order recreation.
- Per-payment leases, apply-time locking and state rechecks protect overlapping
  runs and callbacks. Refund/cancel workflows retain existing behavior.
- Admin displays/filter issues; optional `BOG_RECONCILIATION_ALERT_EMAIL` defaults
  empty (disabled). Problem-only emails use existing delivery, throttled per payment
  and unchanged issue to 24 hours. Job failure/nonexecution alerts are also required.
- No cron provisioned/enabled, no real bank/email calls or remote changes made.
  Production PostgreSQL concurrency verification and activation remain pending.
  Instructions: `docs/PAYMENT_RECONCILIATION.md`. This supersedes the older deferral
  of implementation below, but preserves deferred scheduler activation.

## EasyWay Tracking - 2026-09-22

- EasyWay sync reports: `commerce.EasywaySyncReport`, local migration `0030` applied.
  One private report per changed/problematic batch (or manual refresh), no empty,
  dry-run, skipped-only or unchanged-success reports. Exact counts, up to 50 details,
  safe order links, read-only admin with permission-controlled deletion. Report deletion
  never changes orders/history. Deploy migration before updated command/admin use.
  55 report/tracking/client/shipment tests pass; no remote API calls made for reports.

- `commerce/easyway_tracking.py` reconciles carrier history into existing order
  statuses. No customer-facing carrier text or new public serializer fields.
- `new` preserves the current order state; `taking` advances to processing;
  `taken/in_store/taken_store` advance to shipped; `delivered` advances to delivered.
  `canceled` records carrier cancellation only, with no order/refund/stock action.
- Paid-only forward progress; cancelled/refunding orders and local shipment
  cancellation are protected. Unknown/ambiguous events require admin review.
- Admin refresh and cron share a per-order database lease with short apply-time
  row locking. Preserve tracking fields when saving an older admin form.
- Local migration `commerce.0029_easyway_tracking` applied. 71 targeted tests pass;
  real cancelled shipment tracking was read successfully. Production migration,
  pickup/delivery lifecycle and production PostgreSQL verification remain pending.
- Cron command: `python manage.py sync_easyway_tracking --limit 100 --min-age-minutes 10 --max-seconds 600`.
  Pre-launch: sync every 10 days using the documented daily date-check wrapper,
  anchored to 2026-09-22; first due date 2026-10-02. At public launch switch to the
  direct command and `*/15 * * * *` (UTC). NOT provisioned/enabled.
  Empty batches make no carrier requests. Operator activation/cost review required.
- Deployment instructions and limitations: `docs/EASYWAY_TRACKING.md`.
- User deferred additional cancellation/refund features; do not expand that scope.

## Product Context

This repository is the backend for FlexDrive, an online auto parts store.

Important background:

- The project started from a copied backend of a previous online auto accessories store.
- Much of the existing business logic, API shape, admin behavior, and data model still reflects that earlier auto accessories project.
- The current product direction is a purpose-built auto parts ecommerce platform.
- Existing working ecommerce flows should be preserved unless a requested feature explicitly requires changing them.

Core backend capabilities that should be treated as valuable baseline behavior:

- Customer authentication and registration
- JWT/session-related auth behavior
- Customer profile / account cabinet APIs
- Product catalog APIs
- Cart
- Wishlist
- Checkout / orders / commerce flow
- Django admin and local admin workflows
- Security-related integrations such as reCAPTCHA, which have already been updated with new project keys
- Media/image handling and upload/storage behavior

Do not remove, bypass, or rewrite these areas casually. Preserve working behavior first, then adapt the domain model and API contracts deliberately.

## Technical Context

This is a Django backend using Django REST Framework.

Observed stack and patterns:

- Django 6
- Django REST Framework
- djangorestframework-simplejwt
- django-cors-headers
- python-dotenv based environment configuration
- Cloudinary/Pillow for media-related behavior
- Redis dependency present
- PostgreSQL driver present, with local SQLite development database present in the repository root
- Apps include areas such as `accounts`, `catalog`, `commerce`, `common`, and `pages`

Use the existing Django app boundaries before adding new modules. Prefer extending the relevant existing app when the feature clearly belongs there.

## Backend Working Rules

- Read models, serializers, views, urls, permissions, signals, and tests before changing API behavior.
- Preserve existing API responses expected by the frontend unless a coordinated frontend/backend change is being made.
- Do not change `.env`, secrets, reCAPTCHA keys, JWT signing settings, database credentials, Cloudinary credentials, or deployment secrets.
- Do not hard-code environment-specific URLs or credentials.
- Treat migrations carefully. Add migrations only when model changes require them, and keep them focused.
- Use this repository's virtual environment for Django/backend commands. Run management commands with `.\venv\Scripts\python.exe manage.py ...` from `C:\Users\kench\Desktop\flexdriveback`; do not try system `python` first.
- Do not delete existing fields or endpoints without checking frontend usage first.
- Keep validation in serializers/forms where that is the local pattern.
- Keep business rules server-side even when the frontend also validates them.
- Prefer explicit query optimization for catalog endpoints that return product lists.
- Avoid broad rewrites of working auth, cart, wishlist, checkout, or admin code during redesign-related tasks.

## Auto Parts Domain Direction

The business is no longer a generic auto accessories shop. Future backend work should move the catalog toward auto parts concepts.

Expected domain concepts may include:

- Make / model / year / engine compatibility
- OEM numbers
- Manufacturer part numbers
- Internal SKUs
- Brand / manufacturer
- Category and subcategory hierarchy
- Product condition
- Vehicle side / placement where relevant
- Fitment notes
- Stock status and availability
- Price ranges
- Search keywords and aliases
- Shipping or delivery constraints for large/heavy parts

Do not invent these fields blindly. Before adding schema, inspect existing `catalog` models and current frontend needs. When a new concept is needed, design it so it can support filtering, search, admin editing, and frontend display.

## Catalog And Filtering

Filtering will become a major feature for the auto parts store.

When adding or modifying filters:

- Keep filter parameters stable and documented through code/tests where possible.
- Validate filter values instead of silently accepting invalid combinations.
- Avoid expensive unbounded queries on product list endpoints.
- Consider indexes when adding fields that will be commonly filtered or sorted.
- Keep response payloads suitable for product listing pages: enough information for cards and comparison, without overloading each list item.
- Make frontend and backend naming consistent for categories, brands, compatibility, price, availability, and sorting.

## API Contract With Frontend

The paired frontend repository is expected at:

`C:\Users\kench\Desktop\flexdrivefront`

Frontend and backend are part of the same product effort. When changing an endpoint used by the frontend:

- Inspect frontend usage before modifying the response shape.
- Keep backward compatibility when practical.
- Coordinate breaking changes with frontend edits in the same task.
- Keep error response shapes predictable for forms and checkout flows.
- Ensure auth-protected endpoints continue to return appropriate status codes.

## Admin And Operations

The admin panel is part of the working baseline.

When changing admin-related behavior:

- Preserve staff workflows unless the task asks for a redesign or domain change.
- Make new catalog fields manageable from Django admin when appropriate.
- Keep list displays/search/filtering practical for product and order management.
- Avoid exposing sensitive fields or secrets in admin screens.

## Testing And Verification

Use tests proportional to risk.

For backend changes, consider running or adding tests around:

- Authentication and registration behavior
- Catalog list/detail endpoints
- Filters and sorting
- Cart and wishlist operations
- Checkout/order creation
- Admin-sensitive model behavior
- Security validation such as reCAPTCHA where applicable

If tests cannot be run because of local environment constraints, state that clearly in the final response.

## Session Memory

This file exists so the project context does not need to be re-explained in every Codex session. Treat it as the durable project brief for future work in this backend repository.

## Current Redesign State - 2026-05-01

- Homepage CMS data is being updated to support the FlexDrive redesign while preserving existing ecommerce APIs and admin workflows.
- `ProblemSolving` was renamed/replaced by `CategoryShortcuts`; the old problem-solving content was cleaned up. Category image upload/processing supports the frontend category card slider.
- `ValueProposition` was added as a homepage component between `CategoryShortcuts` and `OrderConfidence`.
  - Migration `pages/migrations/0041_seed_value_proposition_component.py` seeds the component, content `value_proposition_cards`, 3 content items, and homepage ordering.
  - Admin supports image uploads on each value proposition card.
- `OrderConfidence` backend content was refreshed:
  - `pages/migrations/0042_refresh_order_confidence_cards.py` updates card order/copy to process, registration, payment, delivery.
  - `pages/migrations/0043_shorten_order_confidence_registration_title.py` shortens the second title to `რეგისტრაციის გარეშე`.
  - Current expected card titles: `შეკვეთა მარტივად იწყება`, `რეგისტრაციის გარეშე`, `გადახდა შენზეა მორგებული`, `მიწოდება წინასწარ გასაგებია`.
- Staging DB was updated as of 2026-05-01:
  - `pages` migrations are applied through `0043`.
  - `OrderConfidence` title was manually set in staging DB to `შეკვეთა Flex[[Drive]]-ზე მარტივად და გარკვევით` to match local CMS content.
  - If staging UI shows old homepage text, suspect cached `get-current-content` response before changing migrations.
- Frontend no longer visually uses `OrderConfidence.content_items.icon_svg`; keep the field for compatibility unless a later cleanup is explicitly requested.

## Current Static/Legal Content State - 2026-05-15

- Static/legal/support content is being refreshed for FlexDrive while preserving existing CMS/page/component architecture. Frontend still loads backend components by route; do not replace this with hard-coded frontend copy.
- Backend migrations added for the current legal content pass:
  - `pages/migrations/0050_refresh_flexdrive_terms_content.py`
  - `pages/migrations/0051_refine_terms_account_security_copy.py`
  - `pages/migrations/0052_fix_terms_customer_contact_grammar.py`
  - `pages/migrations/0053_refine_terms_installed_part_return_copy.py`
  - `pages/migrations/0054_remove_terms_b2b_future_feature_bullet.py`
  - `pages/migrations/0055_remove_terms_warranty_reference.py`
  - `pages/migrations/0056_refresh_flexdrive_returns_content.py`
  - `pages/migrations/0057_refine_returns_unagreed_shipping_copy.py`
  - `pages/migrations/0058_refine_returns_customer_copy.py`
  - `pages/migrations/0059_refresh_flexdrive_payment_methods_content.py`
  - `pages/migrations/0060_trim_payment_methods_extra_copy.py`
  - `pages/migrations/0061_refresh_flexdrive_privacy_policy_content.py`
  - `pages/migrations/0062_refine_privacy_policy_copy.py`
  - `pages/migrations/0063_refresh_flexdrive_delivery_content.py`
  - `pages/migrations/0064_remove_contact_support_footer_settings_copy.py`
- These migrations were applied locally and on staging Neon/Postgres. If staging still displays old copy, suspect API/browser cache before changing migrations.
- Content direction by page:
  - `/terms`: practical FlexDrive rules for ecommerce use, order confirmation, payment, delivery, returns, B2B, privacy/security. Warranty references were removed because first-phase FlexDrive does not offer a warranty.
  - `/returns`: title is `პროდუქტისა და თანხის დაბრუნება`; ordinary return timing is based on product handover/receipt (`ჩაბარებიდან 14`), not purchase date; installed/used parts are assessed individually; wording avoids making returns feel automatic.
  - `/payment-methods`: reduced to 4 concise sections. Current active method is cash on delivery; card/installment/part-payment copy is future-ready but does not state those methods are already active. Refund/cancel is through the original payment channel for online methods.
  - `/privacy-policy`: reduced to 5 concise sections covering account/profile, cart/wishlist/buy-now, checkout/order, contact inquiries, reCAPTCHA, cookies, analytics/GTM/Google Ads/Meta Pixel, payment providers, delivery partners, retention/security, and user rights.
  - `/delivery`: reduced to 4 concise sections. Delivery timing starts after order confirmation; Tbilisi `1-2 სამუშაო დღე`, regions `4-5 სამუშაო დღე`; old same-day/13:00 logic was removed.
  - `/contact`: `support_intro` no longer has the redundant description about footer settings. The frontend renders this description only when CMS provides non-empty text.
- New legal content should set `ContentItem.icon_svg` to `None`. The redesigned frontend uses Heroicons and ignores backend SVGs for these legal pages.
- Placeholder company/contact data remains until registration and real support details are available. Current placeholders include `support@flexdrive.ge`, `returns@flexdrive.ge`, and `privacy@flexdrive.ge`.
- Tests updated/run during this pass:
  - `pages.test_payment_methods_page`
  - `pages.tests.GetCurrentContentAPITests.test_privacy_policy_page_includes_seeded_component`
  - `pages.tests.GetCurrentContentAPITests.test_delivery_page_includes_seeded_component`
- Next likely content/UI target: footer/contact browser QA if explicitly requested, then payment safety architecture work.

## Current Payment Safety State - 2026-05-15

- Stage 1 of payment safety is implemented as a low-risk foundation:
  - `commerce.Order` now has a separate `payment_status` field with values `pending`, `authorized`, `paid`, `failed`, `cancelled`, `refund_pending`, and `refunded`;
  - cash-on-delivery checkout and buy-now flows still create orders, reduce stock, clear cart/session, and return success through the existing flow;
  - public order summary and authenticated order list/detail serializers expose `payment_status`;
  - Django admin lists, filters, and edits `payment_status` independently from order status;
  - frontend order success, profile order detail, and profile order list display payment status, with `cash_on_delivery + pending` shown as `გადახდა ჩაბარებისას`;
  - guest users still only have the existing per-order success/status page by `public_token`; no guest cabinet was added.
- Local migration `commerce.0010_order_payment_status` was applied during this stage. Staging/prod still need this migration applied during deployment.
- The agreed generic availability copy is: `პროდუქტის ხელმისაწვდომობა შეიცვალა. გთხოვთ გადაამოწმოთ მარაგი და სცადოთ ხელახლა.`
- Payment safety work still not implemented: payment transaction records, reservation expiry, provider abstraction, online card/installment/part-payment callbacks, and refund/cancel provider flows.

## Upcoming Payment Safety Work - 2026-05-15

- Before real card, installment, or part-payment integrations go live, FlexDrive needs a carefully designed payment safety flow. This is high-priority work and must be implemented deliberately, with every step checked end to end.
- The goal is to avoid situations where a customer pays online or receives installment approval for a part that cannot be fulfilled because stock, compatibility, or order validation failed after payment.
- Required planning/implementation areas:
  - stock reservation during checkout, with expiry and release on failed/abandoned payment;
  - separate order status and payment status models/state handling;
  - payment transaction records with provider, provider transaction id, amount, currency, status, timestamps, and raw provider references where appropriate;
  - admin actions for cancelling orders, marking/refunding payments, and clearly tracking refund/cancel state;
  - provider abstraction so a manual/mock provider can exist before TBC/BOG/other real providers are connected;
  - success, failure, cancellation, callback/webhook, refund, and out-of-stock edge cases;
  - customer-facing copy for successful payment, pending confirmation, failed payment, cancelled order, refund initiated, and refund completed states.
- Prefer building the internal safety architecture before bank/provider integration. Bank APIs should plug into an already clear order/payment/refund model rather than defining the whole checkout logic.
- For card payments, prefer authorization/capture if the chosen provider supports it: reserve stock first, authorize payment, then capture only after the order is fulfilment-ready. If immediate capture is required, implement reliable full refund/cancel flows.
- For installments and part-payment providers, cancellation/refund must go through the same provider channel, not manual cash/bank transfer, unless a documented provider exception requires otherwise.
- Do not start this work casually while finishing legal/static pages. Treat it as a separate checkout/payment architecture phase after Terms/Returns/Delivery/Payment/Privacy content is stable and before production payment integrations.

## Current Supplier Import And Staging Media Workflow - 2026-07-02

- Cross Motors supplier refreshes on staging must use the fast bulk importer path, not the old row-by-row importer path.
  - Preferred staging command shape: `.\venv\Scripts\python.exe manage.py import_crossmotors_products --page-size 1000 --sample-size 0 --commit --bulk`
  - Set `DATABASE_URL` only in the command environment for the staging Neon database; do not edit `.env`.
  - Do a dry-run first without `--commit` when changing importer logic or when the supplier feed shape may have changed.
  - Use `--archive-missing` only when explicitly intended; the normal refresh used during this pass did not archive missing feed products.
- The importer now has canonical category mapping to prevent duplicate category creation:
  - Supplier lighting rows should map to `ფარები და განათება` / slug `ganateba`.
  - Supplier bumper/grille visual rows should map to `ვიზუალის ნაწილები` / slug `bamperebi-da-tskhaurebi`.
  - Engine/filter rows should map to `ძრავები და ფილტრები` / slug `dzravi-zetebi-da-filtrebi`.
  - Do not reintroduce fallback category names such as `განათება`, `ბამპერები და ცხაურები`, or `ძრავი, ზეთები და ფილტრები` as new catalog categories.
- If staging categories look wrong after an import, compare SKU-to-category assignments against local by SKU, not only category totals.
  - Ignore non-`CM-*` test products when comparing supplier catalog state.
  - For common `CM-*` SKUs, staging `Product.category.slug` should match local.
  - Local archived supplier leftovers should not be counted as active catalog parity issues.
- Product image sync from local to staging must not be done by copying local DB image paths directly.
  - Local image files are filesystem-backed under `media/`; staging image delivery is Cloudinary-backed.
  - Correct workflow:
    1. Build a local `ProductImage` snapshot keyed by product SKU, including `image_original`, `image_desktop`, `image_tablet`, `image_mobile`, `alt_text`, `is_primary`, and `sort_order`.
    2. Verify every snapshot SKU exists on staging before modifying staging image rows.
    3. Upload local image files to Cloudinary using parallel uploads. Sequential upload is too slow for the current volume.
    4. Only after all uploads succeed, replace staging `ProductImage` rows in one DB transaction: delete old rows, then `bulk_create` the snapshot rows with the uploaded Cloudinary asset paths.
    5. Verify final staging counts by SKU: expected image products, total image rows, no row-count mismatches, and no extra image products.
  - During the 2026-07-02 sync, the expected verified shape was 353 products with images, 1207 `ProductImage` rows, and 4828 Cloudinary files because each row stores original + desktop + tablet + mobile variants.
  - Cloudinary credentials must be supplied only as temporary command environment variables when needed. Never write them into repo files, `.env`, AGENTS.md, scripts, reports, or logs.
  - Temporary sync scripts/snapshots are acceptable for one-off operations, but remove them before finishing unless the user explicitly asks to keep a reusable tool.

## Cross Motors Delayed Stock Protection - 2026-07-27

- Cross Motors API stock is delayed and does not immediately reflect FlexDrive
  sales. Supplier-reported stock and FlexDrive effective stock must remain
  separate.
- `Product.supplier_stock_qty` stores the last raw Cross Motors quantity;
  `Product.stock_qty` stores effective stock after active supplier sale holds.
- Completed Cross Motors order items create a `SupplierStockHold`. The default
  hold window is controlled by `CROSSMOTORS_SALE_HOLD_SECONDS` and defaults to
  24 hours.
- Cross Motors imports must calculate effective stock as raw supplier stock
  minus active holds. Both normal and bulk importer paths must keep identical
  behavior.
- Expired holds are retired only as part of a successful supplier import.
  Supplier API failure must never increase stock from stale data.
- Cancelling/refunding a Cross Motors order releases its hold and recalculates
  from the latest supplier snapshot; never blindly increment supplier stock.
  Manual/local products retain the original stock restoration behavior.
- Django admin exposes supplier stock, active holds, customer-sellable stock,
  last sync time, hold history, and an audited confirmation-protected manual
  release action.

## Deferred Payment Monitoring - 2026-09-18

- The user explicitly deferred automatic payment reconciliation and alerts until
  the production launch phase; there are currently no real buyers. Do not
  implement or provision this work now unless requested.
- Revisit during production deployment planning: periodically check stale or
  unresolved BOG payments against the bank, using the existing verified,
  idempotent reconciliation flow. This must work even if the customer closes
  the browser; a paid cron service is not necessarily required. Choose a
  scheduler after checking hosting capabilities and cost.
- Add operator notifications and clear admin visibility for unresolved failures,
  especially confirmed paid transactions without an order. Rechecking a payment
  must not charge the customer again or blindly recreate a blocked order.
- Existing manual bank reconciliation is available in Django admin. Operators
  currently need to inspect payment transactions, not only the orders list;
  automatic monitoring/alerts are still outstanding.

## Supplier Publication And Scheduled Sync Preparation - 2026-09-22

- Both Cross Motors importer paths now create new products as Draft and preserve
  existing Draft/manual Archived status. Existing Published products still refresh
  supplier price/stock under the existing markup and sale-hold rules.
- `--archive-missing` archives only missing Published CM products and marks
  `Product.supplier_missing=True`. Only these automatically archived products
  republish on return; zero stock alone does not archive a product.
- Admin status changes and publish/draft/block actions clear the automatic-return
  marker. SupplierProductBlock continues to prevent reimport.
- `catalog.0020_product_supplier_missing` is applied locally; deployment must apply
  it before running the updated importer. Existing statuses were not changed.
- The management command locks before fetching (PostgreSQL transaction advisory
  lock; local SQLite file lock). Schedule the command rather than direct helper calls.
- Archive-enabled runs reject empty/no-importable feeds, duplicate SKUs, validation
  errors and a missing share above 20% of Published CM products. A reviewed one-off
  `--max-missing-percent` override exists; do not increase the scheduled threshold
  just to suppress a failed run. Pagination errors and changing snapshot timestamps
  also abort. Silent supplier truncation below the threshold remains a limitation.
- The planned App Platform job runs the bulk command with `--archive-missing`.
  User changed pre-launch cadence to every two days: daily UTC midnight trigger
  plus the documented calendar-parity wrapper runs the import every 48 hours.
  At launch switch to the direct command every two hours. It has NOT been
  provisioned/enabled. Instructions:
  `docs/SUPPLIER_SYNC_APP_PLATFORM.md`.
- Verification: 52 importer/publication/supplier-stock tests passed. Real supplier
  dry run returned 2030 valid rows, 0 errors and 7 missing Published local products.
  No committed supplier refresh or production change was performed.

## Supplier Sync Admin Reports - 2026-09-22

- `SupplierSyncReport` and migration `catalog.0021_supplier_sync_report` add private
  read-only admin history for committed Cross Motors command runs. Dry runs/skipped
  alternate-day launches do not create history. No email/Telegram is sent.
- Reports count new Draft products, customer-sellable stock exhaustion/return,
  archiving/restoration, and supplier price changes. Ordinary quantity changes are
  omitted; each group stores at most 50 names/SKUs plus its exact total count.
- The report and successful import commit together. Failures are saved after rollback
  with a safe phase summary. Database outages/process termination may prevent logging.
- Staff with the appropriate permissions can delete individual/selected/all filtered
  reports through Django admin's normal confirmation flow. Reports have no product
  foreign keys; deletion never deletes products or affects the next sync.

## Shared Cloudinary Product Image Transfer

- Staging and production will share the same Cloudinary cloud. Deploy the shared
  storage protection to BOTH environments before copying image references.
- `CLOUDINARY_SHARED_MEDIA` defaults to True: uploads use fresh UUID-based public
  IDs with overwrite=False; Cloudinary storage deletion becomes a no-op. Existing
  URLs remain valid. Local filesystem deletion behavior is unchanged.
- `audit_cloudinary_orphans --commit` is blocked in shared mode because it only
  checks one database. Future cleanup must account for every sharing environment.
  Unused Cloudinary files are retained for now; direct Cloudinary console changes
  are outside application protection.
- `export_product_images` / `import_product_images` transfer references and all
  ProductImage display/crop/AI settings by SKU. Source and target cloud must match.
  Import defaults to dry-run, only fills empty galleries, skips identical galleries
  on rerun, and refuses conflicting galleries. Missing SKUs require explicit
  `--skip-missing`; no products are created and no price/stock/status is modified.
- Use encoded exports for console transfer; never send credentials in snapshots.
  Instructions: `docs/SHARED_CLOUDINARY_IMAGES.md`. No schema migration required.
- Prepared/tested locally (25 image/storage tests); no remote deploy, image import,
  upload or Cloudinary configuration change has been performed by the agent.

## Individual Product Pricing - 2026-09-28

- User chose product-only markup: category markup no longer participates in admin,
  model or supplier-import pricing. Legacy category column retained unused for
  compatibility. No bulk price-setting action and no pricing-pending UI requested.
- Admin accepts customer amount or percentage with bidirectional live calculation
  and server-side verification. Supplier updates retain the individual percentage:
  supplier 100/customer 120 -> 20%; later supplier 110/customer 132.
- Empty markup means 0%, and new products default to 0%; Cross Motors still creates
  Draft products. User explicitly requested all current products start at 0%.
- Migrations 0025 (10-decimal individual percentage precision) and 0026 (zero default
  and one-time ALL-product reset) applied locally. 2,037 products now have 0%.
  All numeric prices already equalled supplier prices and stayed unchanged; every
  other product field and 26 other catalog/commerce tables verified unchanged by
  hashes. Orders/history unchanged. No remote changes or deployment performed.
- Before remote 0026, snapshot pricing; apply BEFORE setting final per-product
  prices because it resets existing markups once. No automatic data reversal.
  See docs/ADMIN_PRICING.md. Backend pricing/import/SKU checks: 55 passed, one
  PostgreSQL-only concurrency test skipped; 7 JavaScript checks passed.
- Accounting/reporting and historical cost snapshots remain a separate future task.
- Follow-up: admin markup input now displays two decimals while retaining ten-place
  storage/calculation precision. Ordinary saves and supplier-cost edits preserve
  the exact rate; explicit percentage edits replace it. 21 Django pricing tests
  and 8 JavaScript tests passed. No additional migration or price-data change.

## Staging Pricing Rollout Verified - 2026-09-28

- User supplied staging access after pushing the pricing changes. Read-only audit
  found catalog.0025 and 0026 already applied (19:01:11 / 19:01:13 UTC); no migrations
  were rerun and no database rows were changed by the agent.
- Verified PostgreSQL markup column numeric(14,10); all 2,038 products have individual
  0% and customer price equals supplier price. No invalid old_price conflicts.
- Saved a credential-free current pricing snapshot in the local temporary directory.
  This is a post-deployment snapshot, not a pre-migration backup. Admin browser/static
  deployment has not been verified in this database-only audit. Production pending.

## Production Pricing Rollout - 2026-09-28

- Applied catalog.0025_precise_product_markup and catalog.0026_individual_product_pricing
  to the user-supplied production PostgreSQL database in one verified transaction.
- All 2,030 products now have individual 0%; supplier/customer numeric prices already
  matched and remained unchanged. Percentage column verified numeric(14,10).
- Hashes verified every other product field and all 26 other catalog/commerce tables
  unchanged within the transaction. No order/history, stock, provider or scheduler
  actions. No unrelated migrations applied.
- Credential-free pre-change pricing snapshot saved locally at
  C:/Users/kench/AppData/Local/Temp/flexdrive-production-pricing-before-cutover-3da741f831b9430c93c9bf7c5b3f5895.json.
- Database preparation is complete on staging and production. This audit did not
  verify deployed admin/static assets in a browser or initiate a code deployment.

## Accounting Module Stage 1 - 2026-09-29

- User authorized incremental implementation, not the entire module in one task.
  Mandatory STOP for user review before accountant access/groups/account creation.
  Initial reporting routes/exports must be superuser-only; do not expose financial
  data to all staff while accountant permissions are deferred.
- Stage 1 completed: audited commerce models, card snapshot/finalization, direct
  checkout, delivery, refunds, serializers/admin and related tests. Implementation
  plan and acceptance criteria: docs/ACCOUNTING_IMPLEMENTATION_PLAN.md.
- No accounting code/schema/data changes, migrations, remote calls, fixtures or
  user accounts in this stage. Next bounded stage: private historical purchase-cost
  snapshots plus Decimal calculation foundation and targeted regression tests.
- User's workbook rule: gross purchase/1.18 = net cost; gross sale/1.18 = net sale;
  net markup = net sale - net cost. Supplier retail/comparison columns irrelevant.
  VAT registration is planned, effective date unknown. Calculated included purchase
  VAT is separate from invoice-confirmed deductible VAT; no automatic tax return.
- Cost snapshot must be frozen before bank redirection and carried through callback
  normalization/order creation. Preserve in-flight version-1 snapshots; missing
  historical cost stays unknown, never filled using today's supplier price.
- Delivery order fields already exist. Code defaults remain internal fee 0 and
  regional margin 2 (remote effective settings not checked); user intends 10/3.
  Internal carrier cost placeholder 0 is not evidence of zero actual delivery cost.
  Count delivery/buffer once per order, separately from product margins.
- Fake multi-month data and accountant login remain later separate stages. Do not
  create them or deploy accounting changes as part of the next foundation stage.

## Accounting Module Stage 2 - 2026-09-29

- Historical cost/calculation foundation implemented locally. Separate accounting
  screens, report queries, XLSX and accountant access are NOT implemented yet.
- Private OrderItem purchase gross/source/time snapshots are captured before bank
  redirection and copied by verified finalization; direct checkout captures locked
  product values. Old snapshots remain compatible; missing costs stay unknown.
  Model saves preserve snapshots and queryset cost updates are rejected. Existing
  order-item admin inline shows readonly facts; public/bank/receipt fields unchanged.
- Decimal helpers require explicit VAT rates, preserve unknown treatment, match the
  first ten workbook examples and expose rounding residuals: subtract unrounded
  net amounts before rounding markup; reconcile rounded net columns explicitly.
  No VAT registration or deductibility is assumed or activated.
- Local commerce.0033 applied; existing columns in all 27 catalogue/commerce tables
  verified unchanged by hashes; 32 legacy order items remain unknown-cost.
  109 targeted tests passed; two legacy delivery fixtures needed company SKU, then
  passed on rerun. Migration drift/whitespace checks passed. No remote changes.
- Latest user instruction defers 10/3 tariff changes. Reuse dynamic order delivery,
  carrier cost and margin fields. Do not change current pricing defaults/settings.
- Next bounded stage: report queries, date boundaries, delivery and refund/event
  handling, followed by superuser-only UI and export. Stop before accountant access
  for user review. See docs/ACCOUNTING_IMPLEMENTATION_PLAN.md.

## Accounting Module Stage 3 - 2026-09-29

- Added private read-only commerce/accounting_reports.py: inclusive Tbilisi date/
  month periods, order-created reports and separate confirmed cash-event reports.
  Money is grouped by currency; receipt/refund periods remain independent. Delivery
  and regional buffer count once per order. No tariff or checkout changes.
- Full refund allocations require valid sale linkage, matching full amount/currency/
  provider, chronology and unambiguous order transactions. Partial/ambiguous refunds
  and orphan receipts stay visible as unallocated cash with review codes. Missing
  timestamps remain global undated exceptions, not assigned using updated_at.
- Product margin coverage/missing cost and rounding residuals are explicit. Tax
  policy must be supplied using historical treatment; no default 18% activation.
  Internal carrier zero remains unknown actual delivery cost. Order-date totals
  include all statuses and must not be presented as received money or added to cash.
- 24 report tests + 13 foundation tests passed. Tests cover month boundaries,
  cross-month refunds, orphan cash, full/partial/duplicate refunds, currency isolation,
  missing costs, unknown tax, delivery, row limits and fixed query counts (2/4).
  No new migration, business-data write, remote call, provider action or deployment.
- Next stage is the superuser-only admin section; XLSX follows. Neither UI nor
  export exists yet. Do not create accountant access until user review at agreed stop.

## Accounting Module Stage 4 - 2026-09-29

- Separate superuser-only UI now exists at /manager-fd/accounting/, linked from
  admin home. Tabs: summary/orders/products/cash events/exceptions. Active staff AND
  superuser required server-side, with admin login/no-cache; read-only GET endpoint.
  Ordinary staff, even with commerce permissions, cannot access it. No accounts made.
- Date/month/search filters, whole-order search totals, pagination, Georgian labels,
  private detail links and global undated exceptions are implemented. Tax defaults
  unknown; optional clearly labeled 18% hypothetical model previews spreadsheet
  arithmetic without confirming registration/deductibility or changing stored data.
- 51 targeted tests passed. Browser verified month/scenario/search/empty-state/tab
  flows and desktop/mobile layout using an isolated in-memory test database; preview
  server/script removed. No local business-data writes, remote calls or deployment.
- UI needs existing commerce.0033 and new static assets at deployment. Tariffs remain
  unchanged. Next stage: XLSX export; then mandatory review stop BEFORE accountant
  permissions/account. Staging synthetic data remains a later separate stage.

## Accounting Export And Local Demo - 2026-09-29

- XLSX export now available from accounting UI with identical date/search/tax-mode
  filters; all rows, not just current page. Five sheets: summary/orders/products/
  payments-refunds/exceptions. Money is numeric, text explicitly inline (no formula
  injection), headers styled/frozen/filterable. Uses standard-library OOXML writer
  commerce/accounting_export.py; no runtime dependency added. Same superuser gate.
- Three focused export/access/demo create-cleanup tests passed. Prior 51 UI/report/
  foundation tests passed in preceding stage. No remote deployment or new migration.
- User authorized fake data now. Created LOCAL SQLite batch FD-DEMO-202609-:
  7 orders, 9 item rows, 8 mock transactions across July–September 2026. Includes
  pending payment, unknown cost, multiple lines, internal/regional delivery and July
  sale refunded in August. No real product links, stock changes, emails or provider
  calls; no accountant/user created. Demo 10/3 amounts do not change live tariffs.
- Command: accounting_demo (SQLite-only, refuses duplicate batch). Cleanup:
  DATABASE_URL=sqlite:///db.sqlite3 then venv python manage.py accounting_demo --delete.
  Checks demo markers and no real product/payment links before atomic hard-delete;
  tested to preserve unrelated orders. Do not run against remote databases.
- Verified demo totals July–September: orders 424 GEL, received 379, refunded 93,
  net cash 286. Search FD-DEMO-202609- isolates the examples. Fake data remains in
  local db for user review; does not deploy with code. STOP before accountant access.
