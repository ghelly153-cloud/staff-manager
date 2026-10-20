// Common UI primitives, DOM builders, formatting, and dialogs.
// All functions are pure or self-contained.

export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'style') el.style.cssText = v;
    else if (v !== false && v != null) el.setAttribute(k, v === true ? '' : v);
  }
  setKids(el, ...kids);
  return el;
}

export function setKids(el, ...kids) {
  const clean = kids.flat(Infinity).filter(k => k !== null && k !== undefined && k !== false);
  el.replaceChildren(...clean);
}

export function num(x) {
  return (x === null || x === undefined || x === '') ? '—' : Number(x).toLocaleString('en-IN');
}

export function inr(x) {
  if (x === null || x === undefined || x === '') return '—';
  return '₹' + Number(x).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function fdate(iso) {
  if (!iso) return '—';
  const parts = String(iso).split('T')[0].split('-');
  if (parts.length !== 3) return String(iso);
  const [y, m, d] = parts;
  return `${d}/${m}/${y}`;
}

export function today() {
  if (window.__serverToday) return window.__serverToday;
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    }).format(new Date());
  } catch (e) {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }
}

export function badge(text, kind = 'grey') {
  return h('span', { class: `badge b-${kind}` }, text == null ? '—' : String(text));
}

export function statCard(label, val, subtext = '', kind = '') {
  const displayVal = (val === null || val === undefined) ? '—' : String(val);
  return h('div', { class: `stat-card ${kind}` },
    h('div', { class: 'label' }, label),
    h('div', { class: 'val' }, displayVal),
    subtext ? h('div', { class: 'subtext' }, subtext) : null
  );
}

export function policySafeguard(customNotice) {
  return h('div', { class: 'policy-card' },
    h('div', { class: 'policy-icon' }, '§'),
    h('div', { class: 'policy-content' },
      h('h3', {}, 'Financial Policy Safeguard Enforced'),
      h('p', {}, customNotice || 'No employee has an approved compensation rate. No payment amount is authorized, payable, or owed under this policy. Raw workbook values are preserved for operational provenance only, with monetary calculations disabled.')
    )
  );
}

export function empty(title = 'No records found', desc = 'No data matching your current filters.', icon = '📋') {
  return h('div', { class: 'empty' },
    h('div', { class: 'empty-icon' }, icon),
    h('div', { class: 'empty-title' }, title),
    h('div', { class: 'empty-desc' }, desc)
  );
}

export function toast(msg, kind = 'ok') {
  const old = document.querySelector('.toast');
  if (old) old.remove();
  const t = h('div', { class: `toast ${kind}` }, msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

export function modal(title, bodyNode, onSave, saveLabel = 'Save changes') {
  return new Promise(resolve => {
    const prevFocus = document.activeElement;
    const m = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true' });
    
    const close = (val = false) => {
      document.body.classList.remove('modal-open');
      window.removeEventListener('keydown', onKeyDown);
      m.remove();
      if (prevFocus && typeof prevFocus.focus === 'function') {
        try { prevFocus.focus(); } catch (e) {}
      }
      resolve(val);
    };

    const onKeyDown = (e) => {
      if (e.key === 'Escape') close(false);
    };
    window.addEventListener('keydown', onKeyDown);
    document.body.classList.add('modal-open');

    m.addEventListener('click', e => { if (e.target === m) close(false); });
    
    const card = h('div', { class: 'card' },
      h('div', { class: 'modal-header' },
        h('h3', { class: 'modal-title' }, title),
        h('button', { class: 'modal-close-btn', 'aria-label': 'Close dialog', onclick: () => close(false) }, '✕')
      ),
      h('div', { class: 'modal-body' }, bodyNode),
      h('div', { class: 'modal-footer' },
        h('button', { class: 'btn', onclick: () => close(false) }, 'Cancel'),
        onSave ? h('button', {
          class: 'btn pri',
          onclick: async (e) => {
            e.target.disabled = true;
            const originalText = e.target.textContent;
            e.target.textContent = 'Saving…';
            try {
              const ok = await onSave();
              if (ok !== false) { close(true); }
            } finally {
              e.target.disabled = false;
              e.target.textContent = originalText;
            }
          }
        }, saveLabel) : null
      )
    );
    m.appendChild(card);
    document.body.appendChild(m);

    // Auto-focus first input or button in dialog
    setTimeout(() => {
      const focusTarget = card.querySelector('input, select, textarea, button.pri');
      if (focusTarget && typeof focusTarget.focus === 'function') {
        focusTarget.focus();
      }
    }, 50);
  });
}

export function confirmBox(title, msg, confirmText = 'Confirm') {
  return new Promise(resolve => {
    const prevFocus = document.activeElement;
    const m = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true' });
    
    const close = (val) => {
      document.body.classList.remove('modal-open');
      window.removeEventListener('keydown', onKeyDown);
      m.remove();
      if (prevFocus && typeof prevFocus.focus === 'function') {
        try { prevFocus.focus(); } catch (e) {}
      }
      resolve(val);
    };

    const onKeyDown = (e) => {
      if (e.key === 'Escape') close(false);
    };
    window.addEventListener('keydown', onKeyDown);
    document.body.classList.add('modal-open');

    m.addEventListener('click', e => { if (e.target === m) close(false); });
    
    const card = h('div', { class: 'card' },
      h('div', { class: 'modal-header' },
        h('h3', { class: 'modal-title' }, title),
        h('button', { class: 'modal-close-btn', 'aria-label': 'Close dialog', onclick: () => close(false) }, '✕')
      ),
      h('div', { class: 'modal-body' },
        h('p', { style: 'font-size:0.95rem;color:var(--ink);line-height:1.55;margin:0.25rem 0;' }, msg)
      ),
      h('div', { class: 'modal-footer' },
        h('button', { class: 'btn', onclick: () => close(false) }, 'Cancel'),
        h('button', { class: 'btn dng', onclick: () => close(true) }, confirmText)
      )
    );
    m.appendChild(card);
    document.body.appendChild(m);
  });
}

export function qs(obj) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj || {})) {
    if (v !== '' && v !== null && v !== undefined) p.set(k, v);
  }
  return p.toString();
}
