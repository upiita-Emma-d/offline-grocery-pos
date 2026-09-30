# Operations: backups, restore, logs and troubleshooting

## Where things live

| Path | Content |
|---|---|
| `.env` | Configuration and secret key (never commit it) |
| `data/store.sqlite3` | The database: every sale, movement and shift |
| `data/backups/` | Daily verified backups (newest 30 kept) |
| `data/logs/server.log`, `data/logs/backup.log` | Server and backup logs (Windows scripts) |
| `data/media/` | Uploaded product photos |

On Linux the server log is in the journal: `journalctl -u tienda-pos -f`.

## Backups

The scheduled backup runs daily at 22:00 (or at the next start if the laptop was off) and:

1. copies the database with SQLite's online backup API (consistent even while selling),
2. runs `PRAGMA integrity_check` on the copy,
3. prints its SHA-256,
4. keeps the newest 30 copies in `data/backups` and, if `POS_BACKUP_DIR` is set and the drive is connected, 30 more there.

Manual backup at any time:

```powershell
.venv\Scripts\python.exe manage.py backup --dest E:\TiendaPOS-backups
```

**A backup only on the same laptop does not protect against theft or a dead disk.** Keep a USB drive connected (`POS_BACKUP_DIR`) and take a copy home once a week.

## Restore

1. Stop the POS (Windows: `Stop-ScheduledTask TiendaPOS`; Linux: `sudo systemctl stop tienda-pos`).
2. Rename the current `data\store.sqlite3` to `store.sqlite3.broken` (do not delete it yet).
3. Copy the chosen backup to `data\store.sqlite3`.
4. Start the POS and check the latest sales in **Ventas**.

To rehearse it without touching the store: install the POS on another computer, copy a backup to its `data\store.sqlite3` and open it. Do this before relying on the system, and again every few months.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Phones cannot open the POS | Firewall (Windows: run the install script as administrator or add the rule in [installation](installation.md)); laptop IP changed (reserve it in the router and update `POS_ALLOWED_HOSTS`); phone on another network (guest Wi-Fi). |
| `Bad Request (400)` | The address used is not in `POS_ALLOWED_HOSTS`. Add it to `.env` and restart. |
| The page shows old behavior after an update | An old server is still running. Windows: `Get-NetTCPConnection -LocalPort 8008 -State Listen` shows the process; stop it or restart the laptop. |
| "No se pudo imprimir" | Printer off, out of paper or IP changed. The sale is saved; reprint from the ticket. Check with `manage.py test_printer`. |
| "Abre tu turno antes de cobrar" | There is no open shift, or it belongs to another cashier. Open one in **Turnos** with your account. |
| Negative stock on the home screen | More was sold than received: a delivery was not recorded or a code was mis-scanned. Record the receipt or count the product. |
| Forgot a password | Owner: `.venv\Scripts\python.exe manage.py changepassword <user>`. Cashiers: the owner changes it in `/admin/`. |
