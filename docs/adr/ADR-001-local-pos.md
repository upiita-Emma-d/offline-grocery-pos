# ADR-001 — A local, independent POS for a small store

Status: accepted for the pilot, 2026-09-28.

## Context

A small Mexican grocery store needs to record sales, incoming goods and discrepancies in very few steps, on modest hardware, with an existing Epson thermal printer. It must keep working without Internet, with a single register at first. The cashier is not technical and only reads Spanish.

## Decision

- **Django 5.2 LTS, SQLite and server-rendered HTML** with minimal JavaScript. One server process owns the database; browsers on the local network connect to it.
- **A sale is confirmed in one transaction** together with its lines and stock movements. The server prices every line; the browser never sends amounts. Every request carries a **UUID idempotency key**, so a retry returns the original sale instead of charging twice.
- **Prices are frozen per sale line.** Changing the catalog never alters an existing ticket.
- **Stock is derived from movements.** No screen edits a balance directly. Receipts and adjustments always keep user and reason. A physical count records a difference; it never adjusts stock by itself.
- **The ticket is printed after the sale is saved.** A printer failure never rolls the sale back, and reprinting uses the same folio.
- **Checkout works with a touch keyboard, typed codes or a keyboard-wedge barcode scanner.** Enter resolves an **exact** barcode or SKU (leading zeros preserved), never a "similar" product, and every read adds one unit.
- **Product deactivation is reversible:** only by the owner, with zero stock, a reason and an audit record. There is no physical delete in the UI, and an inactive product accepts no stock movements.
- **The Django admin is only for user accounts.** Catalog, sales and movements are operated through domain screens that record author and reason.

## Alternatives considered

- **Native C++ or mobile app:** the latency that matters is human and peripheral, not CPU; maintenance cost would be much higher.
- **Reusing a previous point-of-sale codebase built for fuel stations (.NET/Flutter):** we reuse patterns (identified shift and sale, server-generated ESC/POS tickets), not dependencies.
- **Next.js plus a separate API:** extra processes and coordination with no benefit for one register.
- **A commercial POS:** worth comparing before production if invoicing, card terminals or multiple branches become necessary.

## Consequences

SQLite is enough for one small store with one server process. Before several servers or branches, measure and consider PostgreSQL.
