# Operating rules

These are the business rules the code enforces. Any change to them needs an ADR first (see [AGENTS.md](../AGENTS.md)).

## Accounts and roles

1. Every person signs in with their own account. The **owner** (a Django superuser) manages the catalog, receives goods, counts stock, authorizes returns, registers credit customers, sees reports and settings, and can see every shift. A **cashier** opens and closes their own shift, sells, records cash outs and credit payments in their shift, and sees only their own sales.
2. The Django admin (`/admin/`) is only for creating and editing user accounts.

## Shifts and cash

3. There is one register and one open shift at a time; a day may have several consecutive shifts. The cash in the drawer is the responsibility of whoever opened the shift.
4. Opening and closing are counted by denomination (typing only the total is a fallback). **The closing is blind:** the expected amount appears only in the shift report, after the counted cash is saved.
5. Expected cash = opening float + cash sales − cash returns − cash outs + credit payments received in cash.
6. Every cash out (paying a delivery driver, an expense, a partial drop to a safe) is recorded with a concept. A supplier payment can also be captured when confirming a goods receipt.

## Sales

7. The server prices every sale from the current catalog; the browser never sends amounts. Every request has an idempotency key, so a retry returns the same sale.
8. Enter resolves an **exact** barcode or SKU and adds one unit; a bulk (kg) product opens the grams/amount capture instead. An unknown code shows a warning and adds nothing. Searching by name is always available.
9. "Paga con" only computes the change on screen; it is not stored.
10. Removing a line, lowering a quantity or clearing the sale before charging is logged as a review signal.
11. A sale is **never edited**. A return — partial or full — is linked to the original folio, requires the owner's authorization (their session, or their password typed on the cashier's screen), never exceeds what was sold, and refunds by the original method: cash leaves the open drawer, store credit reduces the debt, card and transfer are refunded outside the system. Each line goes back to the shelf or is recorded as waste. An exchange is a return plus a new sale.

## Stock

12. Stock is the sum of movements; no screen edits it. Negative stock is allowed so the register never stops, but it is flagged on the home screen.
13. Goods enter through **Receiving**: supplier, document and lines are confirmed together with an idempotency key. An unknown code can be assigned to a product without a barcode or created on the spot; an existing barcode is never replaced there. Cost per line is optional; when given it updates the current cost and sales freeze it.
14. A count records expected, counted and difference; it never changes stock. The owner authorizes the adjustment, which applies exactly the recorded difference. Only the latest count of a product can be adjusted.
15. Deactivating a product is reversible, owner-only, needs zero stock and a reason, and is audited. Inactive products accept no stock movements and are not offered at checkout.

## Store credit ("fiado")

16. Only registered, active customers can buy on credit, within their limit if they have one. Only a name or nickname and an optional phone are stored. The balance is computed from credit sales, credit returns and payments; it is never edited.

## Printing

17. Tickets keep the original folio and print after saving. With a network printer configured, the shift opening and the shift report print too. A printer failure never rolls back a sale or a shift, and every attempt is recorded.
