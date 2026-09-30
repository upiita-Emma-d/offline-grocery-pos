# AGENTS.md — Tienda POS

Read `README.md`, `docs/architecture.md`, `docs/operating-rules.md`, `docs/decision-log.md` and the ADRs in `docs/adr/` before changing the product.

## Purpose

A local, independent point of sale for a small store. The priority is recording every sale and every stock movement quickly, and being able to investigate differences between what was received, sold and counted. The cashier uses the checkout screen; the owner manages catalog, receiving, counts, returns and reports.

## Language

- **English:** code identifiers, comments, docstrings, commit messages, documentation and ADRs.
- **Spanish:** everything a store operator sees — templates, UI messages, error messages raised to the UI, ticket and shift-report text, page URLs. The only Spanish document is `docs/guia-rapida-caja.md`, a printable cheat sheet for the cashier.
- Stored choice values are English (`cash`, `piece`); their labels are Spanish.

## Non-negotiable decisions

- Django 5.2 LTS, Python 3.12+, SQLite, one server process (waitress in production). Changing stack or persistence needs a new ADR.
- A sale is confirmed in one transaction with its lines and stock movements. The server computes prices and totals. Every money or stock request has a UUID idempotency key.
- Stock comes from movements; no screen edits it. Receipts and adjustments keep user and reason. A count records a difference before any adjustment, and the adjustment applies the recorded difference.
- Product deactivation is reversible, owner-only, needs zero stock and a reason, and is audited. No physical delete in the UI; no status change from the general product form. Inactive products accept no stock movements.
- A sale is never edited. Returns are linked to the original folio, owner-authorized, never exceed what was sold, and refund by the original method.
- Tickets keep the original folio and print after saving. A printer failure never rolls back a sale or shift. Never create a second sale to reprint.
- Closing captures counted cash before showing the expected amount. One open shift at a time. Expected cash is computed only in `services.shift_summary()`.
- Checkout works with a touch keyboard, typed numbers and a keyboard-wedge scanner. Enter resolves an exact code, never a similar result, and each read adds one unit; a bulk (kg) product opens the grams/amount capture.

## Development

- A material rule change needs an ADR, `docs/decision-log.md` and `docs/operating-rules.md` updated **before** the code.
- Model changes need a migration and an update to the glossary in `docs/architecture.md`.
- Add tests for money, stock, idempotency, permissions and closing. Run `python manage.py test` and `python manage.py check`; for UI changes also run `tools/take_screenshots.py` against a demo store.
- Never commit secrets or real store data: `.env`, `data/` and backups stay out of Git.
- Do not use `/admin/` to alter sales or movements; it is only for user accounts.
- Do not send data to a network printer without knowing its model, IP and protocol.
