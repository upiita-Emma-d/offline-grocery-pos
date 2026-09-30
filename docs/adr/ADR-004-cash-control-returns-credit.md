# ADR-004 — Cash control, returns, store credit, costs and reports

Status: accepted for the pilot, 2026-09-29.

## Context

Delivery drivers are paid with cash from the drawer; without recording it, every closing shows a false shortage. There were no returns: a sale must never be edited, yet customers bring products back. The opening float was recorded only as a total. The store gives credit ("fiado") to fewer than ten people and tracked it on paper. There were no costs or reports.

All of the following follows common retail practice: a sale is immutable, corrections are new documents linked to the original, the cash in the drawer is the responsibility of whoever opened the shift, and every cash movement has a concept and an author.

## Decision

1. **Expected cash** = opening float + cash sales − cash returns − cash outs + store-credit payments received in cash. A single function computes it for both the closing and the shift report.
2. **Cash outs:** supplier payment, expense or partial drop (money moved to a safe). Recorded by whoever operates the shift or by the owner, with a mandatory concept and an idempotency key. A supplier payment can be captured when confirming a goods receipt and stays linked to it.
3. **Returns** (partial or full) are linked to the original folio and **require the owner's authorization**: if the cashier records it, the owner types their username and password on the same screen (supervisor override). Money goes back **by the original payment method**: cash leaves the open shift's drawer; card and transfer are recorded and refunded outside the system; store credit reduces the customer's debt. Each line states whether the product goes back to the shelf (a `return` stock movement) or is waste. A return can never exceed what was sold. Voiding a sale means returning it completely; an exchange is a return plus a new sale.
4. **Cash count by denomination** when opening and closing: bills and coins by piece count; the server computes the total. Typing only the total remains as a fallback. The closing stays blind.
5. **Shift report** ("corte") printed at closing: sales by payment method, returns, cash outs, credit payments, expected, counted, difference, denominations and removed lines.
6. **History and report:** sales filterable by date, shift, cashier and payment method; a daily report with totals, returns, best sellers and margin where costs exist.
7. **Cost per receipt line** is optional. It updates the product's current cost; each sale line freezes the cost for historical margin.
8. **Lines removed before charging** (removed, reduced or cleared) are logged with cashier, product, quantity and shift. They block nothing; they are a signal to review.
9. **Store credit:** the owner registers customers with a name or nickname, optional phone and optional limit. The cashier can sell on credit only to active customers within their limit. Payments are recorded in the open shift; in cash they add to the expected drawer amount. The balance is computed (credit sales − credit returns − payments) and never edited.

## Consequences

- Only minimal customer data is stored: name or nickname and an optional phone.
- The owner-password override has no attempt limit yet; add lockout before real operation.
- Out of scope: integrated card terminal refunds, invoicing (CFDI) and tax withholding.
