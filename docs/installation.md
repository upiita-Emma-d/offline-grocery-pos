# Installing on the store laptop

The POS runs on one computer that is both the server and the register. It was designed for an old laptop: a **2nd-generation Intel Core i3** is plenty for one register.

## 1. Prepare the laptop

| Item | Recommendation |
|---|---|
| Operating system | **Windows 10/11** or **Linux Mint 22 XFCE** (lighter, recommended with 4 GB of RAM). **Windows 7 does not work**: Python 3.12+ and Django 5.2 need Windows 10 or newer. Windows 11 officially rejects 2nd-gen CPUs; use Windows 10 22H2 or Linux. |
| Disk | An **SSD** makes the biggest difference on an old laptop (a 240 GB SATA SSD is inexpensive). |
| RAM | 4 GB works; 8 GB is comfortable if the same laptop is also used for other things. |
| Battery / UPS | A working battery acts as a small UPS. For the router and printer, a small UPS ("no-break") avoids losing a sale in a power cut. |
| Network | Wired or Wi-Fi to the same router as the printer and the phones. |
| Browser | Microsoft Edge (Windows) or Chromium/Firefox (Linux). |

> Windows 10 no longer receives free security updates since October 2025. The POS only listens on the local network, but if the laptop is also used to browse the Internet, Linux Mint is the safer choice.

## 2. Get the code

- With Git: `git clone https://github.com/upiita-Emma-d/offline-grocery-pos.git`
- Without Git: on GitHub, **Code → Download ZIP**, then extract it, for example to `C:\TiendaPOS` or `~/tienda-pos`.

## 3a. Windows 10/11

1. Install Python 3.13: open PowerShell and run `winget install Python.Python.3.13` (or download it from python.org and check **Add python.exe to PATH**).
2. Open PowerShell **as administrator** (right click → Run as administrator) so the firewall rule for phones can be created, then:

   ```powershell
   cd C:\TiendaPOS
   powershell -ExecutionPolicy Bypass -File scripts\windows\install.ps1 -PrinterHost 192.168.1.50 -BackupDir E:\TiendaPOS-backups
   ```

   - `-PrinterHost` is the Epson IP (see [printer.md](printer.md)); omit it to print from the browser.
   - `-BackupDir` is an extra backup folder, ideally a USB drive; omit it to keep backups only in `data\backups`.
   - `-SeedCatalog` loads 93 common grocery products with approximate prices (optional).
   - `-PythonExe C:\path\to\python.exe` if Python is not on the PATH.
3. The script asks you to create the **owner** account. Then it:
   - writes `.env` with a new secret key and the laptop's LAN address,
   - registers the scheduled task **TiendaPOS** (starts the server when you log in) and **TiendaPOS-Backup** (daily at 22:00, or at the next start if the laptop was off),
   - opens TCP port 8008 for private networks so phones can connect,
   - creates a desktop shortcut **Tienda POS** that opens the POS in its own window.

## 3b. Linux (Ubuntu / Linux Mint / Lubuntu)

```bash
sudo apt install python3 python3-venv git
git clone https://github.com/upiita-Emma-d/offline-grocery-pos.git ~/tienda-pos
cd ~/tienda-pos
bash scripts/linux/install.sh --printer-host 192.168.1.50 --backup-dir /media/$USER/USB/tienda-backups
```

It creates the same `.env`, a **systemd** service `tienda-pos` that starts at boot, a timer `tienda-pos-backup` (daily at 22:00), opens the port in `ufw` if it is active, and adds a **Tienda POS** launcher to the menu and desktop. Use `--no-service` to skip systemd and start it by hand with `bash scripts/linux/start.sh`.

## 4. First steps inside the POS

1. Open the **Tienda POS** shortcut (or `http://127.0.0.1:8008/`) and sign in with the owner account.
2. **Configuración:** type the store name, address/phone for the ticket header and the footer message.
3. **Cashier accounts:** go to `http://127.0.0.1:8008/admin/` → Users → Add user. Do **not** tick "Superuser status" for cashiers.
4. **Catalog:** add products in **Productos**, or load the reference list (`-SeedCatalog`) and fix prices. Then scan every product on **Recepción** to attach its real barcode (see the [user guide](user-guide.md#receiving-goods-with-a-phone)).
5. Count the shelves once (**Inventario**) and authorize the adjustments: that is the starting stock.

## 5. Fix the IP addresses

Phones reach the POS at `http://<laptop-ip>:8008/` and the POS reaches the printer at its own IP. If the router hands out different addresses after a restart, both break. In the router (usually `http://192.168.1.254` or `http://192.168.1.1`) create a **DHCP reservation** for the laptop and for the printer. The MAC addresses appear in the router's list of connected devices.

If the laptop's IP changes anyway, add the new one to `POS_ALLOWED_HOSTS` in `.env` and restart the POS.

## 6. Updating to a new version

```powershell
cd C:\TiendaPOS
git pull
powershell -ExecutionPolicy Bypass -File scripts\windows\install.ps1   # re-run: it is idempotent
```

On Linux: `git pull && bash scripts/linux/install.sh`. Migrations run automatically every time the server starts. A backup before updating never hurts: `.venv\Scripts\python.exe manage.py backup`.

## Uninstall (Windows)

```powershell
Unregister-ScheduledTask -TaskName TiendaPOS,TiendaPOS-Backup -Confirm:$false
Remove-NetFirewallRule -DisplayName 'Tienda POS'
```

Then delete the folder, after copying `data\` somewhere safe if you want to keep the history.
