// Goods receiving screen, designed for a phone with a Bluetooth keyboard-wedge scanner.
(() => {
  const search = document.getElementById('search');
  if (!search) return;
  const supplier = document.getElementById('supplier');
  const documentInput = document.getElementById('document');
  const requestId = document.getElementById('request-id');
  const cashPayment = document.getElementById('cash-payment');
  const results = document.getElementById('results');
  const linesBox = document.getElementById('lines');
  const confirmButton = document.getElementById('confirm');
  const status = document.getElementById('status');
  const scanStatus = document.getElementById('scan-status');
  const unknown = document.getElementById('unknown');
  const createForm = document.getElementById('create-form');
  const assignPanel = document.getElementById('assign-panel');
  const assignSearch = document.getElementById('assign-search');
  const assignResults = document.getElementById('assign-results');
  const DRAFT_KEY = 'store-receiving-draft';
  const received = new Map();
  let pendingCode = '';
  let searchTimer;
  let assignTimer;
  let scanQueue = Promise.resolve();

  // 1.005 * 1000 is not an exact integer in floating point; tolerate the representation error.
  function hasThreeDecimalsAtMost(value) { return Math.abs(value * 1000 - Math.round(value * 1000)) < 1e-6; }
  function setText(element, content) { element.textContent = content; return element; }
  function el(tag, className, content) { const e = document.createElement(tag); if (className) e.className = className; if (content !== undefined) setText(e, content); return e; }
  function csrf() { return document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)?.[1] || ''; }
  async function post(url, body) {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify(body) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'No se pudo guardar.');
    return data;
  }

  // The draft keeps the same request id: if the confirmation reached the server but the response
  // was lost, retrying returns the receipt that was already saved.
  function saveDraft() {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ requestId: requestId.value, supplier: supplier.value, document: documentInput.value, cashPayment: cashPayment.value, lines: [...received.values()] })); } catch { /* no local storage */ }
  }
  function deleteDraft() { try { localStorage.removeItem(DRAFT_KEY); } catch { /* no local storage */ } }
  function restoreDraft() {
    try {
      const draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
      if (!draft || !Array.isArray(draft.lines)) return;
      requestId.value = draft.requestId; supplier.value = draft.supplier || ''; documentInput.value = draft.document || ''; cashPayment.value = draft.cashPayment || '';
      draft.lines.forEach(p => received.set(p.id, p));
      if (received.size) setText(status, 'Se recuperó la recepción sin confirmar.');
    } catch { /* unreadable draft: start over */ }
  }

  function addProduct(product) {
    const current = received.get(product.id);
    if (current) current.quantity += 1;
    else received.set(product.id, { id: product.id, name: product.name, sku: product.sku, unit_label: product.unit_label, quantity: 1, cost: '' });
    setText(scanStatus, `+1 ${product.name}`);
    render(); search.focus();
  }
  function render() {
    linesBox.replaceChildren(); let units = 0;
    if (!received.size) linesBox.append(el('p', 'muted', 'Escanea el primer producto.'));
    received.forEach(p => {
      units += p.quantity;
      const row = el('div', 'cart-item receipt-item');
      const name = el('div', '', p.name); name.append(el('small', '', `${p.sku} · ${p.unit_label}`));
      const quantity = el('input'); quantity.type = 'number'; quantity.min = '0.001'; quantity.step = '0.001'; quantity.inputMode = 'decimal'; quantity.value = p.quantity; quantity.setAttribute('aria-label', `Cantidad de ${p.name}`);
      quantity.addEventListener('change', () => { const value = Number(quantity.value); if (!Number.isFinite(value) || value <= 0 || !hasThreeDecimalsAtMost(value)) { quantity.value = p.quantity; return; } p.quantity = value; render(); });
      const cost = el('input'); cost.type = 'number'; cost.min = '0'; cost.step = '0.01'; cost.inputMode = 'decimal'; cost.placeholder = 'Costo c/u'; cost.value = p.cost || ''; cost.setAttribute('aria-label', `Costo por ${p.unit_label} de ${p.name}`);
      cost.addEventListener('change', () => { p.cost = cost.value; saveDraft(); });
      const remove = el('button', 'link-button', '×'); remove.type = 'button'; remove.setAttribute('aria-label', `Quitar ${p.name}`); remove.addEventListener('click', () => { received.delete(p.id); render(); });
      row.append(name, quantity, cost, remove); linesBox.append(row);
    });
    setText(document.getElementById('total'), String(Math.round(units * 1000) / 1000));
    confirmButton.disabled = !received.size;
    saveDraft();
  }
  function listProducts(container, products, onPick, emptyText) {
    container.replaceChildren();
    if (!products.length) { container.append(el('p', 'muted', emptyText)); return; }
    products.forEach(p => {
      const button = el('button', 'result'); button.type = 'button';
      const info = el('span', '', p.name); info.append(el('small', '', `${p.sku} · saldo ${p.stock} ${p.unit_label}`));
      button.append(info); button.addEventListener('click', () => onPick(p)); container.append(button);
    });
  }
  async function searchProducts(q, withoutBarcode) {
    const response = await fetch(`/api/products/?q=${encodeURIComponent(q)}${withoutBarcode ? '&without_barcode=1' : ''}`);
    return (await response.json()).products;
  }
  function hideUnknown() { unknown.hidden = true; createForm.hidden = true; assignPanel.hidden = true; pendingCode = ''; }
  // An unknown code never adds a "similar" product: the owner assigns it or creates the product.
  function showUnknown(code) {
    pendingCode = code; setText(document.getElementById('unknown-code'), code);
    createForm.reset(); createForm.hidden = true; assignPanel.hidden = true; assignResults.replaceChildren(); assignSearch.value = '';
    unknown.hidden = false; setText(scanStatus, '');
  }

  search.addEventListener('input', () => {
    clearTimeout(searchTimer); const q = search.value.trim();
    if (!q) { results.replaceChildren(); return; }
    searchTimer = setTimeout(async () => {
      try {
        const products = await searchProducts(q, false);
        if (search.value.trim() !== q) return;
        listProducts(results, products, p => { search.value = ''; results.replaceChildren(); addProduct(p); }, 'No se encontraron productos.');
      } catch { results.replaceChildren(el('p', 'error', 'No se pudo buscar.')); }
    }, 180);
  });
  async function lookupCode(code) {
    try {
      const response = await fetch(`/api/products/lookup/?code=${encodeURIComponent(code)}`);
      const data = await response.json();
      if (response.status === 404) { showUnknown(code); return; }
      if (!response.ok) throw new Error(data.error || 'No se pudo leer el código.');
      hideUnknown(); addProduct(data.product);
    } catch (error) { setText(scanStatus, error.message); }
  }
  search.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    e.preventDefault(); clearTimeout(searchTimer);
    const code = search.value.trim();
    if (!code) return;
    search.value = ''; results.replaceChildren();
    scanQueue = scanQueue.then(() => lookupCode(code));
  });

  document.getElementById('show-create').addEventListener('click', () => { assignPanel.hidden = true; createForm.hidden = false; createForm.elements.name.focus(); });
  document.getElementById('show-assign').addEventListener('click', () => { createForm.hidden = true; assignPanel.hidden = false; assignSearch.focus(); });
  document.getElementById('dismiss').addEventListener('click', () => { hideUnknown(); search.focus(); });
  createForm.addEventListener('submit', async e => {
    e.preventDefault();
    const button = createForm.querySelector('button'); button.disabled = true;
    try {
      const f = createForm.elements;
      const data = await post('/api/products/quick-create/', { barcode: pendingCode, name: f.name.value, price: f.price.value, unit: f.unit.value, sku: f.sku.value });
      hideUnknown(); addProduct(data.product);
    } catch (error) { setText(scanStatus, error.message); }
    finally { button.disabled = false; }
  });
  assignSearch.addEventListener('input', () => {
    clearTimeout(assignTimer); const q = assignSearch.value.trim();
    if (!q) { assignResults.replaceChildren(); return; }
    assignTimer = setTimeout(async () => {
      try {
        const products = await searchProducts(q, true);
        if (assignSearch.value.trim() !== q) return;
        listProducts(assignResults, products, async p => {
          if (!confirm(`¿Asignar el código ${pendingCode} a «${p.name}»?`)) return;
          try { const data = await post(`/api/products/${p.id}/barcode/`, { barcode: pendingCode }); hideUnknown(); addProduct(data.product); }
          catch (error) { setText(scanStatus, error.message); }
        }, 'Ningún producto sin código coincide.');
      } catch { assignResults.replaceChildren(el('p', 'error', 'No se pudo buscar.')); }
    }, 180);
  });

  supplier.addEventListener('input', saveDraft);
  cashPayment.addEventListener('input', saveDraft);
  documentInput.addEventListener('input', saveDraft);
  document.getElementById('clear').addEventListener('click', () => { if (received.size && !confirm('¿Vaciar la recepción?')) return; received.clear(); render(); });
  confirmButton.addEventListener('click', async () => {
    if (!supplier.value.trim()) { setText(status, 'Indica el proveedor antes de confirmar.'); supplier.focus(); return; }
    confirmButton.disabled = true; setText(status, 'Guardando recepción…');
    try {
      const data = await post('/api/receipts/', { request_id: requestId.value, supplier: supplier.value, document: documentInput.value, cash_payment: cashPayment.value, items: [...received.values()].map(p => ({ product_id: p.id, quantity: p.quantity, cost: p.cost || '' })) });
      deleteDraft(); window.location.assign(data.url);
    } catch (error) { setText(status, error.message); confirmButton.disabled = false; }
  });

  restoreDraft();
  render();
})();
