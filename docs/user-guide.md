# User guide

The screens are in Spanish because the people running the store read Spanish; this guide explains them in English. Screenshots come from the fictitious demo store (`seed_demo`). A printable Spanish cheat sheet for the cashier is in [guia-rapida-caja.md](guia-rapida-caja.md).

**Roles:** the **owner** (propietario) sees every menu. A **cashier** (cajera) sees Caja, Turnos, Ventas and Fiado.

![Login](images/01-login.png)

## A cashier's day

### 1. Open the shift — *Turnos*

Count the float received by denomination: type how many bills and coins of each value there are, and the total adds up by itself. With a network printer, an opening slip prints with signature lines for whoever hands over and whoever receives the money.

Only one shift can be open at a time. The cash in the drawer is the responsibility of whoever opened the shift.

### 2. Sell — *Caja*

![Checkout with cart](images/04-checkout-cart.png)

- **Scan at any time.** The cursor does not need to be in the search box: the POS recognizes the scanner by its typing speed wherever the focus is. A short high beep and a highlighted line confirm each product; a low double beep means the code is unknown.
- Or **type** a code and press Enter: each read adds one unit. An unknown code adds nothing (see below).
- **Search by name**: type a few words in any order (`coca 600`); use ↓ and Enter, or tap the result.
- **− / +** change the quantity without a keyboard; **×** removes a line. Removals are logged for the owner.
- After charging, **scanning the next product on the ticket screen starts the next sale**.
- **Paga con** shows the change to hand back (cash only).
- **Forma de pago:** Efectivo, Tarjeta, Transferencia or Fiado (store credit, then pick the customer).
- **Cobrar venta** saves the sale, prints the ticket and shows it on screen.

**Unknown code:** the warning appears right under the search box. The owner gets **Dar de alta este código**: the product form opens with the barcode filled in, and after saving the POS returns to checkout with the product already in the sale. A cashier is told to search by name or ask the owner.

![Unknown code at checkout](images/20-checkout-unknown-code.png)

**Bulk products (a granel)** such as cheese, ham or produce open a small panel instead of adding 1 kg: type the **grams** from the scale, or the **amount** the customer asks for ("50 pesos of ham"). The server computes the exact price.

![Bulk item by grams](images/03-checkout-bulk.png)

### 3. The ticket

![Sale ticket](images/05-sale-ticket.png)

**Nueva venta** goes back to Caja. **Imprimir ticket** prints through the browser; **Reenviar a Epson** reprints on the network printer with the same folio. **Devolución** starts a return.

### 4. Pay a delivery driver — *Turnos → Salida de efectivo*

When a driver (Bimbo, Coca-Cola, Sabritas…) is paid from the drawer, record it as **Pago a proveedor** with the amount and a concept. Otherwise the closing shows a shortage. Expenses and partial drops to a safe are recorded the same way.

### 5. Close the shift — *Turnos*

![Cash count and cash outs](images/06-shifts-cash-count.png)

Count the drawer (float included) by denomination and press **Cerrar turno e imprimir corte**. The expected amount is **not** shown before counting (blind close). Then the shift report appears and prints:

![Shift report](images/10-shift-report.png)

Expected = opening float + cash sales − cash returns − cash outs + store-credit payments received in cash.

## Returns and exchanges — *Ticket → Devolución*

![Return with owner authorization](images/07-sale-return.png)

Choose how many units come back and whether each goes back to the shelf or is waste (damaged, expired), and write the reason. A cashier needs the **owner's username and password** typed on the same screen. The refund uses the original payment method: cash leaves the drawer, store credit reduces the debt, card and transfer are refunded outside the system. An exchange is a return followed by a new sale.

![Return receipt](images/08-return-receipt.png)

## Store credit — *Fiado*

The owner registers customers (name or nickname, optional phone and limit). At checkout choose **Fiado** and the customer; a sale above the limit is refused. Payments are recorded in the customer's page during an open shift; cash payments add to the drawer.

![Credit customers](images/15-credit-customers.png)
![Customer ledger](images/16-credit-customer-detail.png)

## Owner tasks

### Home

![Owner home](images/09-home-owner.png)

Current shift, recent sales, products below their minimum stock and **negative stock** (sold more than received: a missing receipt or a scanning mistake).

### Receiving goods with a phone — *Recepción*

Open the POS on any phone connected to the store Wi-Fi (`http://<laptop-ip>:8008/`) and pair the Bluetooth scanner with the phone. Type the supplier, then scan every item: each read adds one unit. The cost per piece is optional (it feeds the margin report). If the driver was paid from the drawer, type the amount in **Pagado desde la caja**.

An **unknown barcode** never adds a similar product. The owner can **create** the product right there or **assign** the code to an existing product that has no barcode yet, which is how the reference catalog gets its real barcodes.

<img src="images/18-receiving-phone-unknown-code.png" alt="Receiving on a phone with an unknown code" width="300"> <img src="images/23-receiving-phone-numpad.png" alt="On-screen numeric keypad" width="300"> <img src="images/19-receipt-detail-phone.png" alt="Confirmed receipt on a phone" width="300">

**iPhone + Bluetooth scanner:** iOS treats the scanner as a hardware keyboard and hides its own keyboard. Number fields (quantity, cost, price, cash) therefore open the POS's own **numeric keypad**, and **− / +** adjust quantities. To type text such as a new product's name, tap the keyboard icon ⌨ at the bottom right of the iPhone screen, or switch the scanner off for a moment. Many scanners also have an "iOS keyboard toggle" setup barcode in their manual.

Confirm once at the end. If the connection drops, pressing confirm again never duplicates stock, and an unconfirmed receipt is recovered after reloading the page.

### Counting stock — *Inventario*

![Inventory count](images/14-inventory-count.png)

Scan or search the product and type how many are physically there. The count records the difference but **does not change stock** until you press **Autorizar ajuste**. Only the latest count of a product can be adjusted.

### Catalog — *Productos*

![Price change](images/22-catalog-price-change.png)

**Change a price:** open **Productos** and scan the product (or search it). A single match puts the cursor straight in its price box: type the new price and press Enter. The message shows the old and new price, the search is kept for the next product, the history is saved and old tickets never change. **Editar** shows the price history.

**Add a product:** **+ Nuevo producto**, scan the barcode (the scan fills the field and jumps to the name), type name and price, choose the unit (piece, kg for bulk, liter, pack). The internal SKU, cost, minimum stock and photo are optional under "Más datos"; an empty SKU becomes the barcode or an automatic `P00001`-style code. **Guardar y dar de alta otro** keeps you in the form for the next product.

![New product](images/21-product-new.png)

**Dar de baja** removes a product from checkout; it needs zero stock and a reason and can be reversed.

### Sales history and daily report — *Ventas*, *Reporte*

![Sales history](images/12-sales-history.png)
![Daily report](images/11-daily-report.png)

Filter sales by dates, folio, shift, cashier or payment method. The report shows net sales, the average ticket, totals by payment method, best sellers, margin where costs exist, shifts with their differences, cash outs and removed lines per cashier.

### Ticket text — *Configuración*

![Store settings](images/17-store-settings.png)

Store name, header lines (address, phone, hours) and footer message, with a live preview. They apply to the next ticket.

### Cashier accounts

`/admin/` → Users → Add user. Leave "Superuser status" unticked for cashiers.
