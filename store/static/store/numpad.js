// On-screen numeric keypad for touch devices (ADR-006). When a Bluetooth scanner is paired with an
// iPhone, iOS treats it as a hardware keyboard and hides its own keyboard, so number fields could not be
// filled. Fields marked with data-numpad use this keypad on touch screens; desktops are unaffected.
(() => {
  if (!window.matchMedia('(pointer: coarse)').matches) return;
  let field = null;
  let text = '';

  const sheet = document.createElement('div');
  sheet.className = 'numpad';
  sheet.hidden = true;
  sheet.innerHTML = '<div class="numpad-display"><span class="numpad-label"></span><strong class="numpad-value"></strong></div>'
    + '<div class="numpad-keys">' + ['1', '2', '3', '4', '5', '6', '7', '8', '9', '.', '0', '⌫'].map(k => `<button type="button" data-key="${k}">${k}</button>`).join('')
    + '<button type="button" class="primary numpad-done" data-key="done">Listo</button></div>';
  document.body.append(sheet);
  const label = sheet.querySelector('.numpad-label');
  const value = sheet.querySelector('.numpad-value');

  function prepare(root) {
    // inputmode="none" keeps the native keyboard closed; hardware keys (the scanner) still type.
    root.querySelectorAll?.('[data-numpad]').forEach(input => input.setAttribute('inputmode', 'none'));
  }
  prepare(document);
  new MutationObserver(records => records.forEach(r => r.addedNodes.forEach(node => {
    if (node.nodeType !== 1) return;
    if (node.matches('[data-numpad]')) node.setAttribute('inputmode', 'none');
    prepare(node);
  }))).observe(document.body, { childList: true, subtree: true });

  function labelFor(input) {
    return input.getAttribute('aria-label') || input.closest('label')?.firstChild?.textContent?.trim() || input.placeholder || '';
  }
  function open(input) {
    field = input;
    text = input.value || '';
    setText(label, labelFor(input));
    render();
    sheet.hidden = false;
    document.body.classList.add('numpad-open');
    // Keep the field being edited visible above the keypad.
    requestAnimationFrame(() => input.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  }
  function close() {
    if (field) field.dispatchEvent(new Event('change', { bubbles: true }));
    field = null;
    hide();
  }
  function hide() {
    sheet.hidden = true;
    document.body.classList.remove('numpad-open');
  }
  function setText(element, content) { element.textContent = content; }
  function render() { setText(value, text || '0'); }
  function commit() {
    // Number inputs reject partial values such as "12."; keep the text here and write only valid numbers.
    const clean = text.endsWith('.') ? text.slice(0, -1) : text;
    if (clean === '' || !Number.isNaN(Number(clean))) {
      field.value = clean;
      field.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  document.addEventListener('focusin', event => { if (event.target.matches?.('[data-numpad]')) open(event.target); });
  // Tapping elsewhere (for example "Cobrar" or "Confirmar") commits the value right away but hides the
  // keypad a moment later: hiding it at once shifts the layout and the tap would miss its button.
  document.addEventListener('pointerdown', event => {
    if (!field || sheet.contains(event.target) || event.target === field) return;
    field.dispatchEvent(new Event('change', { bubbles: true }));
    field = null;
    setTimeout(() => { if (!field) hide(); }, 300);
  });
  // Keep the focus on the field while tapping the keypad.
  sheet.addEventListener('pointerdown', event => event.preventDefault());
  sheet.addEventListener('click', event => {
    const key = event.target.closest('button')?.dataset.key;
    if (!key || !field) return;
    if (key === 'done') { close(); return; }
    if (key === '⌫') text = text.slice(0, -1);
    else if (key === '.') { if (!text.includes('.') && field.step !== '1') text = (text || '0') + '.'; }
    else text = text === '0' ? key : text + key;
    render();
    commit();
  });
  // A hardware keyboard (or the scanner) typing into the field keeps the display in sync.
  document.addEventListener('input', event => { if (event.target === field && event.isTrusted) { text = field.value; render(); } });
})();
