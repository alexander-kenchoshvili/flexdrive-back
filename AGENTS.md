# Project Instructions

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
- Apps include areas such as `accounts`, `catalog`, `commerce`, `common`, `employees`, `pages`, and `projects`

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
