# Offline return walkthrough

Run `venv\Scripts\python.exe scripts\returns_preview.py` from the backend root.
Open http://127.0.0.1:8011/manager-fd/commerce/order/ . This is a separate
loopback-only process, automatically signed in as a throwaway demo superuser.
Do not expose or proxy this server to a network. Stop its process when finished.

Each launch creates a NEW temporary SQLite database and three synthetic orders.
It never copies or connects to the existing local or remote database. No .env
changes; fake-bank patching exists only inside this standalone process.
Outbound socket connections and DNS lookups are blocked before Django initializes;
mail, storage and all caches are local. Browser CSP blocks external subresources.
The yellow banner identifies this environment. Ordinary admin remains unchanged
and must NOT be used for this offline walkthrough.

- TEST-01: not purchased. Open refund, select not purchased, confirm not dispatched.
  Submit. Owned stock stays zero. Use the bank-status check and confirm to simulate
  bank completion; the supplier hold releases and the order becomes refunded.
- TEST-02: already purchased/on hand. Select on-hand and confirm not dispatched.
  Submit: one unit enters FlexDrive stock. Bank-status check simulates completion
  without adding another unit.
- TEST-03: delivered. Start return, then open the waiting list. Receive one saleable
  unit and zero unsaleable; confirm inspection. The stock list gains one unit.
  Separately submit the refund and bank-status check to simulate completion.

All bank operations on this port are simulations, even though ordinary admin labels
still say BOG. The status-check button deliberately completes a requested fake
refund, allowing inspection of the pending state before confirmation.
`--check` runs all three admin scenarios in its own fresh database and checks that
outbound socket/DNS calls are denied. It does not start a browser or server and
does not consume the three orders in the separately launched preview.
