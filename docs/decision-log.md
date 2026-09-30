# Decision log

## Accepted

- [ADR-001](adr/ADR-001-local-pos.md) — Local Django + SQLite monolith, server-priced idempotent sales, stock from movements, print after save, exact barcode reads, reversible deactivation.
- [ADR-002](adr/ADR-002-receiving-and-hardware.md) — One computer as server and register; grouped, idempotent goods receipts; unknown codes assigned or created while receiving; adjustments apply the recorded count difference.
- [ADR-003](adr/ADR-003-bulk-sales.md) — Bulk products sold by grams or amount; closed unit list; one product per selling unit.
- [ADR-004](adr/ADR-004-cash-control-returns-credit.md) — Cash outs, owner-authorized returns, cash count by denomination, printable shift report, history and daily report, costs, removed-line log, store credit.
- [ADR-006](adr/ADR-006-scanner-first-ux.md) — Scans captured wherever the focus is; scan on the ticket starts a new sale; beeps; create unknown codes from checkout; steppers and on-screen numeric keypad; optional SKU; price changes keep the search.
- [ADR-005](adr/ADR-005-english-codebase-and-deployment.md) — English code and docs with Spanish UI; waitress + WhiteNoise in production; install scripts for Windows and Linux; ESC/POS network printing with accents.

## Closed questions

- Tablet or Raspberry Pi as the store device → one laptop (ADR-002, ADR-005).
- Phone camera scanning → not needed; a Bluetooth keyboard-wedge scanner works on the laptop and on iPhones (ADR-002).
- Epson model and connection → Epson TM-T88V on the LAN, ESC/POS over TCP 9100, 42 columns (ADR-005). Accents (Windows-1252) still to be confirmed on paper.

## Open

- Attempt limit (lockout) for the owner-password override on returns.
- Invoicing (CFDI), taxes and discounts.
- Supplier accounts payable (buying on credit) and authorization by amount.
- HTTPS or an isolated network before exposing the POS beyond a trusted home/store Wi-Fi.
- Restore drill on another computer, on a schedule.
- Signed initial stock count before relying on stock differences.
