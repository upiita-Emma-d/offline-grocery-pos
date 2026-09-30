# Development

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip ...
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py seed_catalog --with-stock <owner-username>   # optional sample data
.venv/bin/python manage.py runserver
```

Without a `.env`, the project runs in development mode (`POS_DEBUG=1`) with a random secret key stored in `data/`. `POS_DATA_DIR` points the database, backups and photos somewhere else, which is handy for throwaway demos.

## Try the demo store

```bash
export POS_DATA_DIR=/tmp/tienda-demo                  # an EMPTY folder
python manage.py migrate
python manage.py seed_demo --owner-password <owner> --cashier-password <cashier>
python manage.py runserver
```

`seed_demo` creates the fictitious store "Abarrotes La Esquina": owner `admin`, cashier `lupita`, the reference catalog with stock and fake barcodes (`0000000000017` Coca-Cola, `0000000000024` Sabritas, `0000000000031` milk, `0000000000048` Gansito, `0000000000055` cheese by weight), two credit customers, a closed shift with sales, a return and cash outs, and an open shift ready to sell. It refuses to run on a database that already has sales.

## Tests

```bash
python manage.py test      # unit and HTTP tests (money, stock, idempotency, permissions, closing, printing)
python manage.py check
python manage.py makemigrations --check --dry-run
```

Printing tests replace `socket.create_connection` with a fake printer; they never touch the network.

### Browser walkthrough and screenshots

`tools/take_screenshots.py` drives the real UI with Playwright and Microsoft Edge: it searches, scans, weighs cheese, charges, records a cash out, authorizes a return, counts stock and receives goods on a phone-sized screen. It fails if the browser reports a JavaScript error or the server answers 5xx, and it refreshes the images in `docs/images/`.

```bash
python -m venv .screenshots-venv && .screenshots-venv/bin/pip install playwright
# terminal 1: demo store on port 8010
POS_DATA_DIR=/tmp/tienda-demo python manage.py runserver 127.0.0.1:8010
# terminal 2
.screenshots-venv/bin/python tools/take_screenshots.py --owner-password <owner> --cashier-password <cashier>
```

It uses the installed Edge (`channel='msedge'`); on Linux run `playwright install chromium` and change the channel.

## Conventions

- **English** for code, comments, commits and documentation. **Spanish** for everything an operator sees: templates, messages, ticket text, page URLs. Stored choice values are English with Spanish labels.
- Money and stock only change inside `store/services.py`, in a transaction, with an idempotency key.
- A material rule change needs an ADR in `docs/adr/`, an entry in `docs/decision-log.md` and an update to `docs/operating-rules.md` **before** the code.
- Model changes need a migration and an update to the glossary in `docs/architecture.md`.
- Add tests for money, stock, idempotency, permissions and closing.
- Never commit `.env`, `data/`, backups or real store data.
