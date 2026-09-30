# ADR-003 — Bulk sales by grams or amount

Status: accepted for the pilot, 2026-09-29. Refines the scanning rule of ADR-001.

## Context

Cheese, ham, loose eggs, fruit and vegetables are weighed on a plain (unconnected) scale. Prices are per kilogram and quantities accept three decimals, but checkout added 1 kg when the product was picked, and the cashier had to convert grams to kilograms mentally. Customers also ask for an amount ("50 pesos of ham").

## Decision

1. A product is **bulk** when its unit is `kg`. Its price is per kilogram and its stock is kept in kilograms with three decimals (grams).
2. At checkout, picking or scanning a bulk product **does not add one unit**: it opens a **grams or amount** capture. Pieces, packs and liters keep the one-unit-per-read rule.
3. By amount, the quantity is converted to the nearest gram (`amount ÷ price per kg`, three decimals). The server computes the subtotal from that quantity and rounds to cents; it may differ by a few cents from the amount asked, and the ticket shows the real amount. The browser never sends amounts.
4. Units come from a closed list (piece, kg, liter, pack) so `kg` cannot be typed several ways.
5. Each product is counted in one unit only. An item sold both loose and packed (loose eggs and a 12-egg pack) is two products.

## Alternatives

- A scale connected by serial or USB: depends on the model; postponed.
- Price-embedded EAN-13 labels: requires a label-printing scale.
- Price per 100 g: confusing when comparing with supplier prices per kilogram.
