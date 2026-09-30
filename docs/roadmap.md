# Roadmap

## Done — pilot-ready demo

- Checkout with search, exact barcode reads, bulk items by grams or amount, change helper, cash/card/transfer/store credit.
- Shifts with cash count by denomination, blind closing and printable shift report; cash outs.
- Returns linked to the original folio with owner authorization; waste vs. restock.
- Goods receiving on a phone with a Bluetooth scanner, costs per line, unknown-code assignment.
- Stock counts with authorized adjustments; negative-stock alerts.
- Sales history with filters; daily report with best sellers and margin.
- ESC/POS network printing (Epson TM-T88V) with accents; customizable ticket header and footer.
- Install scripts for Windows 10/11 and Linux with autostart and daily verified backups.
- 49 automated tests plus a browser end-to-end walkthrough (`tools/take_screenshots.py`).

## Next — pilot at the store

1. Install on the store laptop (see [installation](installation.md)); fix the laptop and printer IPs in the router.
2. Load the real catalog: scan every product on **Recepción** to assign its real barcode; review prices.
3. Signed initial count. For two weeks compare receipts, sales and counts for a sample of high-shrink products.
4. Rehearse failures: printer off, Wi-Fi down, power cut, restore a backup on another computer.

**Exit criteria:** reproducible daily closing, readable tickets, explainable differences, a restored backup and no duplicated sales on retries.

## Later

- Lockout for repeated wrong owner passwords.
- Discounts, supplier credit, invoicing and taxes if the store needs them.
- Stock rotation and suggested purchase lists from reliable data.
- PostgreSQL only if several registers or branches appear.
