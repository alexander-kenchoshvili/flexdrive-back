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