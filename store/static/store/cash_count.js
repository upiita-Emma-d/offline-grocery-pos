// Adds up the cash count on screen as a guide; the server recomputes the total from the pieces.
(() => {
  document.querySelectorAll('[data-cash-count]').forEach(box => {
    const pieces = box.querySelectorAll('[data-value]');
    const total = box.querySelector('[data-total]');
    const amount = box.querySelector('[data-amount]');
    const money = v => new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(v);
    function update() {
      let cents = 0; let any = false;
      pieces.forEach(p => { const n = Number(p.value); if (p.value && Number.isInteger(n) && n > 0) { any = true; cents += n * Math.round(Number(p.dataset.value) * 100); } });
      total.textContent = any ? money(cents / 100) : (amount.value ? money(Number(amount.value)) : money(0));
      // The typed total is a fallback; it lives inside a closed <details>, so it is never "required".
      amount.disabled = any;
    }
    pieces.forEach(p => p.addEventListener('input', update));
    amount.addEventListener('input', update);
    update();
  });
})();
