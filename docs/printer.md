# Thermal printer

The POS talks **ESC/POS over TCP port 9100**, the raw protocol of Epson TM receipt printers with an Ethernet or Wi-Fi interface. It was verified on an **Epson TM-T88V** (80 mm paper). Without a network printer, every ticket can still be printed from the browser to any printer installed in the operating system.

## What gets printed

| When | Document |
|---|---|
| Charging a sale | Sale ticket: store header, folio, date, cashier, lines, item count, total, payment method, customer balance for store credit, footer |
| Opening a shift | Opening slip: shift, cashier, bills and coins, opening float, signature lines |
| Closing a shift | Shift report: sales by method, returns, cash outs, credit payments, expected, counted, difference, cash count, signatures |
| On demand | Reprint from the ticket or the shift report (same folio, never a new sale) |

A printer that is off, out of paper or unreachable never blocks a sale or a shift: the operation is saved, a warning appears and the attempt is recorded.

## 1. Find the printer's IP address

Any of these works:

- **Status sheet:** with the printer on, press the small button on the network interface at the back for less than 3 seconds. It prints the IP address.
- **Router:** look for a device named `EPSON…` in the router's list of connected clients.
- **Network scan** (what we did for the TM-T88V): list hosts with TCP 9100 open. On Windows PowerShell:

  ```powershell
  1..254 | ForEach-Object { $ip = "192.168.1.$_"; $c = New-Object Net.Sockets.TcpClient; if ($c.ConnectAsync($ip, 9100).Wait(150)) { "open: $ip" }; $c.Close() }
  ```

  Connecting without sending data prints nothing. Epson MAC addresses start with `00:26:AB`, `50:57:9C`, `64:EB:8C` and others registered to Seiko Epson.

Reserve that IP in the router (DHCP reservation) so it never changes.

## 2. Configure

In `.env` next to `manage.py`:

```ini
POS_PRINTER_HOST=192.168.1.50
POS_PRINTER_PORT=9100
POS_PRINTER_COLUMNS=42     # 80 mm paper, font A. Use 32 for 58 mm paper.
POS_PRINTER_ACCENTS=1      # Windows-1252 code page: á é í ó ú ñ ¡ ¿
```

Restart the POS (Windows: `Stop-ScheduledTask TiendaPOS; Start-ScheduledTask TiendaPOS`; Linux: `sudo systemctl restart tienda-pos`).

## 3. Test

```powershell
.venv\Scripts\python.exe manage.py test_printer
```

The test page shows the configured columns and a line of digits:

- the digits fill exactly one line → the column count is right;
- they wrap to a second line → lower `POS_PRINTER_COLUMNS` (32 for 58 mm);
- lots of space is left on the right → try 48.

It also prints accents; if they come out as symbols, set `POS_PRINTER_ACCENTS=0` (plain ASCII).

## Details

- The paper is cut with `GS V 66` (feed to the cutter, then partial cut). The simpler `GS V 1` cuts at the print head and leaves the last lines inside the printer, at the top of the next ticket. The half centimeter after the last line is the head-to-cutter distance.
- The store name prints in double size and wraps to half the columns; the header and footer lines wrap to the full width.
- Ticket text comes from **Configuración** in the POS; no restart needed.
- USB-only printers: use the browser's **Imprimir ticket** button with the printer installed in Windows. Set margins to none, disable headers and footers, and choose the roll paper size; Edge remembers it.
