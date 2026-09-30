# Architecture

## Overview

```
 Phones (iPhone / Android)         Store laptop (Windows 10/11 or Linux)
 ┌──────────────────────┐          ┌────────────────────────────────────────────┐
 │ Safari / Chrome      │   Wi-Fi  │ Browser (Edge --app)  ← cashier            │
 │ + Bluetooth scanner  │ ───────► │ waitress :8008 → Django (config/, store/)  │
 └──────────────────────┘   LAN    │ SQLite  data/store.sqlite3                 │
                                   │ Scheduled backup → data/backups, USB drive │
                                   └──────────────┬─────────────────────────────┘
                                                  │ ESC/POS over TCP 9100
                                                  ▼
                                        Epson TM-T88V (network)
```

- **One process owns the database.** SQLite is enough for one register; waitress serves requests with a few threads and SQLite waits up to 20 s for a write lock.
- **Server-rendered pages** (Django templates, Spanish text) plus three small vanilla JavaScript files: `checkout.js`, `receiving.js` and `cash_count.js`. No build step and no CDN, so it works offline.
- **The browser never decides money.** It sends product ids and quantities; `store/services.py` prices, validates and saves everything inside transactions.

## Code layout

| Path | What lives there |
|---|---|
| `config/` | Django settings (reads `.env`), URLs, WSGI entry point |
| `store/models.py` | Domain model (see below) |
| `store/services.py` | All operations that touch money or stock, cash-count math, shift summary, ESC/POS printing |
| `store/views.py`, `store/urls.py` | HTTP layer: permissions, forms, JSON APIs |
| `store/templates/` | Spanish UI |
| `store/static/store/` | `style.css` and the three scripts |
| `store/management/commands/` | `backup`, `seed_catalog`, `seed_demo`, `test_printer` |
| `store/tests.py` | Unit and HTTP tests |
| `scripts/` | Install, start and backup scripts for Windows and Linux |
| `tools/take_screenshots.py` | Playwright walkthrough that also acts as an end-to-end test |

## Domain model

| Model | Purpose |
|---|---|
| `Product` | SKU, optional unique barcode, unit (`piece`, `kg`, `liter`, `pack`), price, current cost, minimum stock, active flag. Stock is computed from movements. |
| `StockMovement` | Signed quantity with kind `receipt`, `sale`, `adjustment` or `return`, reason, author and optional links to sale, receipt or return. |
| `GoodsReceipt` | One delivery: supplier, document, author; groups `receipt` movements. |
| `StockCount` | Expected, counted and difference; optional link to its adjustment movement. |
| `Shift` | Cashier, opening float and denomination counts, counted/expected cash and difference. One open shift per register (database constraint). |
| `Sale`, `SaleLine` | Immutable sale with payment method and optional credit customer; lines snapshot SKU, name, unit price and unit cost. |
| `SaleReturn`, `ReturnLine` | Return linked to a sale, refund method, authorizer; each line restocks or is waste. |
| `CashOut` | Supplier payment, expense or drop taken from a shift's drawer. |
| `Customer`, `CreditPayment` | Store-credit customers and their payments. |
| `RemovedLine` | Items removed or reduced before charging. |
| `PriceChange`, `ProductStatusChange` | Audit trail for prices and deactivation/reactivation. |
| `PrintAttempt` | Result of every ticket, shift-opening, shift-report or test print. |
| `StoreSettings` | Single row with the store name, ticket header and footer. |

## Invariants worth knowing

- **Idempotency:** `Sale`, `GoodsReceipt`, `SaleReturn`, `CashOut`, `CreditPayment` and `RemovedLine` have a unique `request_id`. `services.idempotent()` returns the existing record on a retry, including the race where two submissions arrive at once.
- **Rounding:** subtotals round half-up to cents. Returning the remainder of a line refunds exactly `subtotal − already refunded`, so partial returns never drift by a cent.
- **Expected cash** has a single source: `services.shift_summary()`.
- **Blind close:** the shift report view refuses to render an open shift.
- **Printing** happens after the transaction commits; failures are recorded in `PrintAttempt` and shown as a warning.

## UI glossary (Spanish UI ↔ code)

| UI (Spanish) | Code | Meaning |
|---|---|---|
| Caja | `checkout` | Selling screen |
| Turno, abrir/cerrar | `Shift`, `open` / `close_shift` | Cashier session with its drawer |
| Fondo inicial | `opening_float` | Cash in the drawer at opening |
| Arqueo | `cash count` (`opening_count`, `closing_count`) | Count by denomination |
| Corte | `shift_report` | Printable closing summary |
| Salida de efectivo | `CashOut` | Money taken from the drawer |
| Pago a proveedor / Gasto / Retiro parcial | `supplier_payment` / `expense` / `drop` | Cash-out kinds |
| Venta, folio | `Sale`, `id` | A sale and its number |
| Efectivo / Tarjeta / Transferencia / Fiado | `cash` / `card` / `transfer` / `credit` | Payment methods |
| Fiado, abono | store credit, `CreditPayment` | Credit sale and a payment towards it |
| Devolución, merma | `SaleReturn`, `restock=False` | Return; item written off |
| Recepción | `GoodsReceipt` / `receiving` | Incoming goods |
| Conteo, ajuste | `StockCount`, `adjustment` | Physical count and its correction |
| Existencia | `stock` | Stock on hand |
| Clave | `sku` | Internal product code |
| A granel | bulk (`unit='kg'`) | Sold by weight |
| Baja / reactivación | `deactivate` / `reactivate` | Reversible product removal |
| Renglones quitados | `RemovedLine` | Items removed before charging |
