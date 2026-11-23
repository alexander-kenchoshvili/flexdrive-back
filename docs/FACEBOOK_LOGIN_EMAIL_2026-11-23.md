# Facebook Login access and missing email — 2026-11-23

## Observed production evidence

- Public backend OAuth start returned 302 to Meta app `1321658899670696`,
  Graph API `v25.0`, `scope=email,public_profile`, `response_type=code`, and
  `https://flexdrive.ge/auth/facebook/callback`.
- Meta dashboard showed Published, business verified, no required actions and
  no restriction alert. Both permissions were initially **Ready for testing**.
- User authorized increasing the existing permissions. **Increase access** was
  performed separately for `email` and `public_profile`. User personally completed
  Meta's password reauthentication. Both permissions became **Ready to publish**,
  and this persisted after navigating away and back. Publish page still offered
  only **Unpublish**; no republish/unpublish was performed.
- Friend's subsequent attempt moved past Meta's original Feature unavailable
  screen and reached the site's Georgian missing-email error. User reports the
  friend has a Facebook email and allowed its sharing. This does not independently
  establish what the OAuth token's actual `email` grant status was.
- Existing serializer rejects a profile without email before creating/linking an
  account. The exact Georgian error maps to that validation branch, not to a
  redirect/cookie failure. The existing callback does not inspect `/me/permissions`,
  so historical logs cannot establish why email was omitted.
- DigitalOcean live backend and frontend were Healthy. Backend overview lists
  managed PostgreSQL `flexdrive-prod-db` and Valkey `flexdrive-prod-valkey` on
  DigitalOcean. Runtime log search found no `Facebook profile fetch failed` match
  in the available sample. This is not proof of an error-free full history.
- No production DB, order, payment, provider token, deployment or environment
  mutation was performed. No credentials/customer payloads were saved here.

## Prepared source change (not deployed)

Backend reads `/me/permissions` **only after a valid OAuth callback returns an ID
but no email**. Existing emailed profiles keep the same successful flow and no
extra request. Fixed result enum: `granted`, `declined`, `expired`, `not_granted`,
`unavailable`. Malformed, duplicate, oversized, redirected or failed responses are
unavailable, not evidence of a refusal. Bearer token stays in the request header;
no provider response/ID/email/code/token/raw exception is returned or logged.

One redacted warning identifies the missing-email outcome:

```text
facebook_email_missing permission_status=granted rerequest=False
```

Frontend displays separate Georgian explanations for a grant without returned
email, missing/declined/expired grant, unavailable grant check, and unsuccessful
re-request. It offers an explanation and explicitly clicked retry only for the
three missing-grant outcomes. The retry uses `rerequest_email=1` ->
`auth_type=rerequest`; scope stays `email,public_profile`. Retry context is in the
signed OAuth state. A failed retry returns to the site without another automatic
permission dialog. No fake email, bypassed verification or account creation on
missing-email outcomes is introduced.

## Rollout and remaining diagnosis

Deploy **both repositories**; no migration or new ENV. Existing repository workflow
leaves push/deploy to the user. Backend-first is safe but old frontend will use a
generic explanation for the new error codes until frontend is deployed.

Repeat one consented friend attempt after deployment and inspect the fixed enum.
`granted` plus missing email means Meta did not supply email despite the token's
grant; a re-request is not offered for that outcome. Do not claim a historical
decline, missing account email, or successful registration without fresh evidence.
Supporting a separately verified email-completion flow is not implemented here.

## Data Use Checkup remains pending

Increasing access created an annual Data Use Checkup due **2027-01-22**. Its
business verification step is complete. Data handling questions remain incomplete.
User confirms no national-security disclosure of user data to authorities in the
last 12 months. Internal authority-request procedures have not been established;
do not certify invented policies. User asked to prioritize the actual login issue.
No usage/terms attestation or final submission was made. The future checkup
deadline is not evidence that it currently caused the missing-email error.

## References

- [Meta manual Login flow, including declined permission re-request](https://developers.facebook.com/documentation/facebook-login/guides/advanced/manual-flow)
- [Meta permission handling](https://developers.facebook.com/documentation/facebook-login/guides/permissions/request-revoke)
- [Meta email permission and consent example](https://developers.facebook.com/docs/graph-api/get-started/)

## Validation

- 12 Facebook auth/permission/recovery backend tests; 14 existing Google auth and
  Facebook deletion checks. Malformed status types added to the permission tests.
- 3 frontend tests execute the real translation utility, actual Vue Facebook
  button SSR, and shared OAuth button click/URL builder. No live Meta event or
  customer authentication is fabricated by tests.
- Scoped frontend ESLint, app vue-tsc and whitespace checks passed. The final
  malformed-status test rerun passed all 7 new backend tests (overlapping the
  initial 12). No full build or storefront visual automation was run.
- User reconfirmed they will push and deploy both repositories. Remote branch
  heads were checked read-only and matched the local base commits. No commit,
  push or deployment was performed by the agent.
