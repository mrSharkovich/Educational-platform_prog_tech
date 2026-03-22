/* ── API helpers ─────────────────────────────────────────── */
const api = {
  async post(url, data) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return r.json();
  },
  async get(url) {
    const r = await fetch(url);
    return r.json();
  }
};

/* ── Toast notifications ─────────────────────────────────── */
function toast(msg, type = 'success') {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const t = document.createElement('div');
  const icon = type === 'success' ? '✓' : '✕';
  t.className = `toast toast-${type}`;
  t.innerHTML = `<span>${icon}</span>${msg}`;
  container.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

/* ── Button loading state ────────────────────────────────── */
function btnLoad(btn, loading) {
  if (loading) {
    btn._text = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span>';
    btn.disabled = true;
  } else {
    btn.innerHTML = btn._text;
    btn.disabled = false;
  }
}
