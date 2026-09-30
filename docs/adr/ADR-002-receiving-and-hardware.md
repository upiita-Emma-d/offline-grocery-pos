# ADR-002 — Grouped receiving, shared scanner and one store computer

Status: accepted for the pilot, 2026-09-29.

## Context

Incoming goods were recorded product by product, repeating the invoice in every line and without an idempotency key, so a Wi-Fi retry could duplicate stock. Nothing tied the movements of one delivery together.

The adjustment of a count recalculated the difference against the stock at authorization time; sales made between counting and authorizing were silently erased.

The store will buy a single device. The family uses iPhones, native apps cannot be distributed, and a 1D/2D scanner with Bluetooth, 2.4 GHz dongle and cable (keyboard-wedge mode) was bought.

## Decision

1. **One computer is both server and register.** The Epson and the scanner connect to it. Phones join through the browser on the local network and can use the same scanner over Bluetooth. A tablet cannot be the server, so none is bought.
2. **Goods receipt.** A receipt groups one delivery: supplier, document (invoice or note), user, date and lines. It is confirmed in one transaction with an idempotency key. Each line creates a `receipt` stock movement. Only the owner receives goods, and only for active products.
3. **Unknown code while receiving.** The owner can assign it to an active product that has no barcode yet, or create the product on the same screen. An existing barcode is never replaced there, and a "similar" product is never chosen.
4. **Counting by code.** Inventory searches by exact barcode, SKU or name. An adjustment applies the difference **recorded when counting**. Only the most recent count of a product can be adjusted; older unadjusted counts become superseded.
5. **Change helper.** For cash, the cashier may type the amount received to see the change. It is a screen aid only; it is not stored and never alters the server-computed total.
6. **Negative stock** is shown separately on the home screen as an anomaly.

## Alternatives

- Phone camera scanning: needs HTTPS with a certificate installed on every iPhone plus a decoding library. Discarded while the Bluetooth scanner covers the need.
- Native Kotlin or Swift apps: cannot be distributed to the iPhones without a store.
- Tablet as register plus a separate server: two devices for the price of one, with no benefit for one register.
