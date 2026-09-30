// Scanner-first input (ADR-006). A keyboard-wedge scanner "types" a code much faster than a person and
// ends with Enter. Recognizing that burst lets every screen react to a scan wherever the focus is,
// instead of silently losing it when the cursor is not in the search box.
(() => {
  const MAX_GAP_MS = 50;   // scanners send a key every ~5-30 ms; people type far slower
  const MIN_LENGTH = 6;    // EAN-8 is the shortest retail barcode
  const handlers = [];
  let buffer = '';
  let lastKeyAt = 0;
  let target = null;
  let targetValue = '';

  function reset(event) {
    buffer = '';
    target = event ? event.target : null;
    targetValue = target && 'value' in target ? target.value : '';
  }

  document.addEventListener('keydown', event => {
    if (!handlers.length || event.ctrlKey || event.metaKey || event.altKey) return;
    const now = performance.now();
    const gap = now - lastKeyAt;
    lastKeyAt = now;
    if (event.key === 'Enter') {
      if (buffer.length >= MIN_LENGTH && gap < MAX_GAP_MS * 3) {
        // Take the burst back out of whatever field it landed in, then handle it as a scan.
        event.preventDefault();
        event.stopImmediatePropagation();
        if (target && 'value' in target && target.value !== targetValue) {
          target.value = targetValue;
          target.dispatchEvent(new Event('input', { bubbles: true }));
        }
        const code = buffer;
        reset();
        handlers.forEach(handler => handler(code));
        return;
      }
      reset();
      return;
    }
    if (event.key.length !== 1) { reset(); return; }
    if (gap > MAX_GAP_MS) reset(event);
    buffer += event.key;
  }, true);

  let audio = null;
  function beep(ok) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const tones = ok ? [[1320, 0, 0.07]] : [[220, 0, 0.12], [220, 0.18, 0.12]];
      tones.forEach(([frequency, start, length]) => {
        const oscillator = audio.createOscillator();
        const gain = audio.createGain();
        oscillator.frequency.value = frequency;
        gain.gain.value = 0.08;
        oscillator.connect(gain).connect(audio.destination);
        oscillator.start(audio.currentTime + start);
        oscillator.stop(audio.currentTime + start + length);
      });
    } catch { /* audio not available: the visual feedback is enough */ }
  }

  window.PosScanner = {
    onScan(handler) { handlers.push(handler); },
    beep,
    // Screens where a scan should start a sale (home, ticket) just send it to the checkout.
    startSale(checkoutUrl) { handlers.push(code => { window.location.assign(`${checkoutUrl}?scan=${encodeURIComponent(code)}`); }); },
  };
})();
