# ADR-006 — Scanner-first user experience

Status: accepted, 2026-09-30. Refines ADR-001 (exact reads) and ADR-003 (bulk capture).

## Context

Field testing at the store showed that the POS looked broken when it was not:

- At checkout, a scan only worked while the search box had focus. After touching the payment selector, a quantity or any button, scans went nowhere.
- After charging, scanning the next customer's first item on the ticket screen did nothing.
- Paired with an iPhone, the Bluetooth scanner is a hardware keyboard, so iOS hides the on-screen keyboard. Quantities, costs and prices could not be typed.
- Scanning into the barcode field of the product form submitted the form (the scanner sends Enter) before the name and price were typed.
- Creating a product required an internal SKU first, and changing a price lost the search after saving.

## Decision

1. **Scans are captured on every scanner-enabled screen, wherever the focus is.** A scan is recognized as a burst of at least 6 characters typed less than 50 ms apart and ending with Enter; people do not type that fast. The burst is removed from whatever field it landed in and handled as a code. Slower typing keeps working as before, so typing a code and pressing Enter in the search box still resolves an exact code.
2. **Where a scan goes:** checkout adds the product (exact match only, as in ADR-001); the ticket and home screens start a new sale with the scanned product; receiving adds one unit; inventory and catalog search the exact code; the product form fills the barcode field and moves to the name.
3. **Feedback:** a short high beep and a highlighted line when a product is added, a low double beep and a red message when a code is unknown.
4. **Unknown code at checkout:** the owner gets "Dar de alta este código", which opens the product form with the barcode filled in and returns to checkout with the new product already added. A cashier is told to search by name or ask the owner. Checkout never adds a similar product.
5. **No-keyboard operation:** quantity steppers (− / +) for pieces at checkout and receiving; on touch devices, number fields open the app's own numeric keypad (the native keyboard is suppressed with `inputmode="none"`). Text fields still need the system keyboard; the UI explains how to show it on iOS while a scanner is connected.
6. **Product creation:** the SKU is optional; when empty it becomes the barcode or, without one, the next free `P00001`-style code. The form is ordered by frequency of use (barcode, name, price, unit); cost, minimum stock and photo are optional extras. "Guardar y dar de alta otro" keeps the owner in the form.
7. **Price change:** saving keeps the catalog search, the message shows the old and new price, and the product form lists the recent price history.

## Consequences

- A person typing six or more characters faster than 50 ms per key would be treated as a scan; that does not happen in practice.
- `store/static/store/scanner.js` and `numpad.js` are loaded by every page; each screen decides what a scan means.
