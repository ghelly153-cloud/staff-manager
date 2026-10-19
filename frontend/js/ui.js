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
  return (x === null || x === undefined) ? '—' : Number(x).toLocaleString('en-IN');
}

export function inr(x) {
  if (x === null || x === undefined) return '—';
  return '₹' + Number(x).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function fdate(iso) {
  if (!iso) return '—';
  const [y, m, d] = String(iso).split('-');
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

export function today() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function badge(text, kind = 'grey') {
  return h('span', { class: `badge b-${kind}` }, text);
}

export function statCard(label, val, subtext = '', kind = '') {
  return h('div', { class: `stat-card ${kind}` },
    h('div', { class: 'label' }, label),
    h('div', { class: 'val' }, String(val)),
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
    const m = h('div', { class: 'modal' });
    const close = () => { m.remove(); resolve(false); };
    m.addEventListener('click', e => { if (e.target === m) close(); });
    
    const card = h('div', { class: 'card' },
      h('div', { class: 'card-header' },
        h('h3', { class: 'card-title' }, title),
        h('button', { class: 'btn sm', onclick: close }, '✕')
      ),
      h('div', { style: 'margin-bottom:1.25rem' }, bodyNode),
      h('div', { style: 'display:flex;justify-content:flex-end;gap:0.5rem' },
        h('button', { class: 'btn', onclick: close }, 'Cancel'),
        onSave ? h('button', {
          class: 'btn pri',
          onclick: async (e) => {
            e.target.disabled = true;
            try {
              const ok = await onSave();
              if (ok !== false) { m.remove(); resolve(true); }
            } finally {
              e.target.disabled = false;
            }
          }
        }, saveLabel) : null
      )
    );
    m.appendChild(card);
    document.body.appendChild(m);
  });
}

export function confirmBox(title, msg, confirmText = 'Confirm') {
  return new Promise(resolve => {
    const m = h('div', { class: 'modal' });
    const close = (val) => { m.remove(); resolve(val); };
    m.addEventListener('click', e => { if (e.target === m) close(false); });
    
    const card = h('div', { class: 'card' },
      h('div', { class: 'card-header' },
        h('h3', { class: 'card-title' }, title),
        h('button', { class: 'btn sm', onclick: () => close(false) }, '✕')
      ),
      h('p', { style: 'font-size:0.92rem;color:var(--ink);margin-bottom:1.5rem;line-height:1.5' }, msg),
      h('div', { style: 'display:flex;justify-content:flex-end;gap:0.5rem' },
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
