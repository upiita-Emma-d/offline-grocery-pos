// Checkout screen. The browser only collects product ids and quantities; the server prices the sale.
// Visible messages are Spanish because the cashier's UI is Spanish.
(() => {
  const search = document.getElementById('search');
  if (!search) return;
  const results = document.getElementById('results');
  const linesBox = document.getElementById('lines');
  const chargeButton = document.getElementById('charge');
  const status = document.getElementById('status');
  const unknown = document.getElementById('unknown');
  const payment = document.getElementById('payment');
  const paidWith = document.getElementById('paid-with');
  const change = document.getElementById('change');
  const creditBox = document.getElementById('credit-box');
  const customer = document.getElementById('customer');
  const urls = document.getElementById('product-new-url').dataset;
  const isOwner = document.body.hasAttribute('data-owner');
  const cart = new Map();
  let found = [];
  let searchTimer;
  let scanQueue = Promise.resolve();
  let cartTotal = 0;
  let lastAddedId = null;

  // crypto.randomUUID only exists over HTTPS; getRandomValues also works on the local network over HTTP.
  function newUuid() {
    const b = crypto.getRandomValues(new Uint8Array(16)); b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    const h = [...b].map(x => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }
  function csrf() { return document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)?.[1] || ''; }
  function setText(element, content) { element.textContent = content; return element; }
  function el(tag, className, content) { const e = document.createElement(tag); if (className) e.className = className; if (content !== undefined) setText(e, content); return e; }
  function money(value) { return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(value); }
  function round(value, decimals) { const factor = 10 ** decimals; return Math.round((value + Number.EPSILON) * factor) / factor; }
  // 1.005 * 1000 is not an exact integer in floating point; tolerate the representation error.
  function hasThreeDecimalsAtMost(value) { return Math.abs(value * 1000 - Math.round(value * 1000)) < 1e-6; }
  function setStatus(text, kind) { setText(status, text); status.className = kind === 'error' ? 'error-text' : 'muted'; }

  // Removing, reducing or clearing before charging is logged as a review signal; it never blocks the sale.
  function logRemoved(product, quantity, reason) {
    if (!(quantity > 0)) return;
    fetch('/api/removed-lines/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify({ request_id: newUuid(), product_id: product.id, quantity: round(quantity, 3), reason }) }).catch(() => {});
  }

  function addQuantity(product, quantity) {
    const current = cart.get(product.id);
    if (current) current.quantity = round(current.quantity + quantity, 3);
    else cart.set(product.id, { ...product, quantity });
    lastAddedId = product.id;
    unknown.hidden = true;
    renderCart();
  }
  // A bulk (kg) product never adds 1 kg: it opens the grams/amount capture (ADR-003).
  function addProduct(product, clearSearch = true) {
    if (clearSearch) search.value = '';
    results.replaceChildren(el('p', 'muted', 'Escribe para buscar un producto.'));
    if (product.is_bulk) { openBulk(product); return; }
    addQuantity(product, 1); search.focus();
  }

  const bulkPanel = document.getElementById('bulk-panel');
  const bulkGrams = document.getElementById('bulk-grams');
  const bulkAmount = document.getElementById('bulk-amount');
  const bulkSummary = document.getElementById('bulk-summary');
  const bulkAdd = document.getElementById('bulk-add');
  let bulkProduct = null;
  let bulkKilos = 0;
  function openBulk(product) {
    bulkProduct = product; bulkKilos = 0;
    setText(document.getElementById('bulk-name'), `${product.name} · ${money(Number(product.price))}/kg`);
    bulkGrams.value = ''; bulkAmount.value = ''; computeBulk();
    bulkPanel.hidden = false; bulkGrams.focus();
  }
  function closeBulk() { bulkProduct = null; bulkPanel.hidden = true; search.focus(); }
  function computeBulk() {
    const price = Number(bulkProduct?.price || 0);
    const grams = Number(bulkGrams.value);
    const amount = Number(bulkAmount.value);
    bulkKilos = 0;
    if (bulkGrams.value && Number.isFinite(grams) && grams > 0) bulkKilos = round(Math.round(grams) / 1000, 3);
    else if (bulkAmount.value && Number.isFinite(amount) && amount > 0 && price > 0) bulkKilos = round(amount / price, 3);
    bulkAdd.disabled = bulkKilos <= 0;
    if (bulkKilos <= 0) { setText(bulkSummary, '—'); return; }
    const subtotal = round(bulkKilos * price, 2);
    const asked = !bulkGrams.value && bulkAmount.value ? ` (pidió ${money(amount)})` : '';
    setText(bulkSummary, `${bulkKilos.toFixed(3)} kg = ${money(subtotal)}${asked}`);
  }
  bulkGrams.addEventListener('input', () => { if (bulkGrams.value) bulkAmount.value = ''; computeBulk(); });
  bulkAmount.addEventListener('input', () => { if (bulkAmount.value) bulkGrams.value = ''; computeBulk(); });
  bulkPanel.addEventListener('submit', e => {
    e.preventDefault();
    if (!bulkProduct || bulkKilos <= 0) return;
    const name = bulkProduct.name;
    addQuantity(bulkProduct, bulkKilos); setStatus(`${bulkKilos.toFixed(3)} kg de ${name} agregado.`); window.PosScanner.beep(true); closeBulk();
  });
  document.getElementById('bulk-cancel').addEventListener('click', closeBulk);
  bulkPanel.addEventListener('keydown', e => { if (e.key === 'Escape') closeBulk(); });

  function renderResults() {
    results.replaceChildren();
    if (!found.length) { results.append(el('p', 'muted', 'No se encontraron productos.')); return; }
    found.forEach(p => {
      const button = el('button', 'result'); button.type = 'button';
      const info = el('span', '', p.name); info.append(el('small', '', `${p.sku} · disponible ${p.stock} ${p.unit_label}`));
      button.append(info, el('strong', '', money(Number(p.price)))); button.addEventListener('click', () => addProduct(p)); results.append(button);
    });
  }
  // Arrow keys move between the search box and the results; Enter on a result picks it.
  search.addEventListener('keydown', e => { if (e.key === 'ArrowDown') { const first = results.querySelector('.result'); if (first) { e.preventDefault(); first.focus(); } } });
  results.addEventListener('keydown', e => {
    if (!e.target.matches('.result') || !['ArrowDown', 'ArrowUp'].includes(e.key)) return;
    e.preventDefault();
    const next = e.key === 'ArrowDown' ? e.target.nextElementSibling : e.target.previousElementSibling;
    (next || (e.key === 'ArrowUp' ? search : e.target)).focus();
  });

  function stepper(p, delta) {
    const value = round(p.quantity + delta, 3);
    if (value <= 0) return;
    if (delta < 0) logRemoved(p, -delta, 'reduced');
    p.quantity = value; lastAddedId = null; renderCart();
  }
  function renderCart() {
    linesBox.replaceChildren(); let total = 0;
    if (!cart.size) linesBox.append(el('p', 'muted', 'Agrega el primer producto.'));
    cart.forEach(p => {
      total += p.quantity * Number(p.price);
      const row = el('div', 'cart-item' + (p.id === lastAddedId ? ' flash' : ''));
      const name = el('div', '', p.name); name.append(el('small', '', `${money(Number(p.price))} / ${p.unit_label}`));
      const quantityBox = el('div', 'qty');
      const quantity = el('input'); quantity.type = 'number'; quantity.min = '0.001'; quantity.step = p.is_bulk ? '0.001' : '1'; quantity.value = p.quantity; quantity.dataset.numpad = ''; quantity.setAttribute('aria-label', `Cantidad de ${p.name}`);
      quantity.addEventListener('change', () => {
        const value = Number(quantity.value);
        if (!Number.isFinite(value) || value <= 0 || !hasThreeDecimalsAtMost(value)) { quantity.value = p.quantity; return; }
        if (value < p.quantity) logRemoved(p, p.quantity - value, 'reduced');
        p.quantity = value; lastAddedId = null; renderCart();
      });
      if (p.is_bulk) quantityBox.append(quantity);
      else {
        const minus = el('button', 'step', '−'); minus.type = 'button'; minus.setAttribute('aria-label', `Una menos de ${p.name}`); minus.addEventListener('click', () => stepper(p, -1));
        const plus = el('button', 'step', '+'); plus.type = 'button'; plus.setAttribute('aria-label', `Una más de ${p.name}`); plus.addEventListener('click', () => stepper(p, 1));
        quantityBox.append(minus, quantity, plus);
      }
      const remove = el('button', 'link-button', '×'); remove.type = 'button'; remove.setAttribute('aria-label', `Quitar ${p.name}`);
      remove.addEventListener('click', () => { logRemoved(p, p.quantity, 'removed'); cart.delete(p.id); lastAddedId = null; renderCart(); });
      row.append(name, quantityBox, el('strong', '', money(p.quantity * Number(p.price))), remove); linesBox.append(row);
    });
    cartTotal = Math.round(total * 100) / 100;
    setText(document.getElementById('total'), money(total)); chargeButton.disabled = !cart.size;
    renderChange();
  }
  // Only a helper for the cashier: the server computes the total and the change is not stored.
  function renderChange() {
    document.getElementById('cash-box').hidden = payment.value !== 'cash';
    if (creditBox) creditBox.hidden = payment.value !== 'credit';
    const received = Number(paidWith.value);
    change.classList.remove('error');
    if (!paidWith.value || !Number.isFinite(received) || !cart.size) { setText(change, '—'); return; }
    const difference = Math.round((received - cartTotal) * 100) / 100;
    if (difference < 0) { change.classList.add('error'); setText(change, `Faltan ${money(-difference)}`); }
    else setText(change, money(difference));
  }
  paidWith.addEventListener('input', renderChange);
  payment.addEventListener('change', renderChange);

  search.addEventListener('input', () => {
    clearTimeout(searchTimer); const q = search.value.trim();
    if (!q) { found = []; results.replaceChildren(el('p', 'muted', 'Escribe para buscar un producto.')); return; }
    searchTimer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/products/?q=${encodeURIComponent(q)}`);
        const data = await response.json();
        if (search.value.trim() !== q) return;
        found = data.products; renderResults();
      } catch { results.replaceChildren(el('p', 'error', 'No se pudo buscar.')); }
    }, 180);
  });

  // An unknown code adds nothing (ADR-001). The owner can create it and come straight back (ADR-006).
  function showUnknown(code) {
    unknown.replaceChildren();
    const message = el('p'); message.append(el('strong', '', `Código ${code} no registrado.`), document.createTextNode(' No se agregó nada.'));
    unknown.append(message);
    if (isOwner) {
      const link = el('a', 'primary button', 'Dar de alta este código');
      link.href = `${urls.url}?barcode=${encodeURIComponent(code)}&next=${encodeURIComponent(urls.checkout)}`;
      unknown.append(link);
    } else {
      unknown.append(el('p', 'muted', 'Búscalo por nombre en el cuadro de arriba, o pide al dueño que lo registre.'));
    }
    unknown.hidden = false;
  }
  async function lookupCode(code) {
    setStatus(`Buscando código ${code}…`);
    try {
      const response = await fetch(`/api/products/lookup/?code=${encodeURIComponent(code)}`);
      const data = await response.json();
      if (response.status === 404) { setStatus(''); showUnknown(code); window.PosScanner.beep(false); return; }
      if (!response.ok) throw new Error(data.error || 'No se pudo leer el código.');
      addProduct(data.product, false);
      window.PosScanner.beep(true);
      setStatus(data.product.is_bulk ? `${data.product.name}: captura gramos o importe.` : `${data.product.name} agregado.`);
    } catch (error) { setStatus(error.message, 'error'); window.PosScanner.beep(false); }
  }
  function queueLookup(code) { scanQueue = scanQueue.then(() => lookupCode(code)); }
  // Scans are recognized wherever the focus is (scanner.js); typing a code and pressing Enter also works.
  window.PosScanner.onScan(code => { search.value = ''; queueLookup(code); });
  search.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    e.preventDefault(); clearTimeout(searchTimer);
    const code = search.value.trim();
    if (!code) return;
    search.value = ''; found = [];
    queueLookup(code);
  });
  document.getElementById('clear').addEventListener('click', () => { cart.forEach(p => logRemoved(p, p.quantity, 'cleared')); cart.clear(); paidWith.value = ''; renderCart(); });
  chargeButton.addEventListener('click', async () => {
    if (payment.value === 'credit' && !customer?.value) { setStatus('Elige el cliente de fiado.', 'error'); return; }
    chargeButton.disabled = true; setStatus('Guardando venta…');
    try {
      const body = { request_id: document.getElementById('request-id').value, payment: payment.value, customer_id: payment.value === 'credit' ? customer.value : null, items: [...cart.values()].map(p => ({ product_id: p.id, quantity: p.quantity })) };
      const response = await fetch('/api/sales/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify(body) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'No se pudo registrar la venta.');
      window.location.assign(data.ticket_url);
    } catch (error) { setStatus(error.message, 'error'); chargeButton.disabled = false; }
  });

  // A scan made on the ticket or home screen, or a product just created from here, arrives as ?scan=CODE.
  const pending = new URLSearchParams(window.location.search).get('scan');
  if (pending) { history.replaceState(null, '', window.location.pathname); queueLookup(pending); }
})();
