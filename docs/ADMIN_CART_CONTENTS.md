# Admin cart contents — 2026-11-24

The existing `/manager-fd/commerce/cart/` list now has a Contents filter:
With products (`?contents=nonempty`), Empty (`?contents=empty`), or All.
It combines with the existing active filter and owner search. The default remains
All; no cart records are hidden by default or deleted.

Rows show the existing account representation, or an explicit unknown guest,
product names and public FD codes with quantities and product-admin links,
distinct product count and summed unit count. Preview shows at most five products
per cart, with a link to the cart and the remaining count. All inline products
remain available in the existing cart detail page. Product text is HTML escaped.
The guest token remains in the detail and existing search, rather than occupying
the list. Existing cart permissions and edit actions remain in force.

This is current saved cart contents, not an add/remove event history, a unique
buyer count, a live online indicator, an abandonment report or a purchase count.
Accounts identify the attached account; guest identities are unknown. Existing
header loading requests a cart; `resolve_cart` creates an empty cart when no
usable saved cart is found. `is_active` means the cart can still be used, including
when empty. None of these collection/lifecycle rules changed.

The repository already contains `cleanup_carts`; its production scheduling was
not inspected and it was not executed. No retention change or production cleanup
was performed.

Validation: 5 new cart-admin tests plus 8 existing admin navigation/timezone tests
pass with an explicitly isolated in-memory SQLite database. Covers empty/nonempty
and active filter combinations, counts, existing owner search, guest/account
labels, escaping, public codes, bounded previews, two batched queries with no
queries per rendered row, and denied access without cart permission. Existing
CKEditor and missing-staticfiles warnings remain. No browser/full build performed.

Requires backend push/deploy by the user. No frontend, migration, environment,
production database, payment/provider or cart-creation change; no push/deploy run.
