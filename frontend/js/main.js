// Main router, shell renderer, authentication handling, and SSE subscription.
import { api } from './api.js';
import { h, setKids, toast } from './ui.js';
import { renderHome, renderEmployees, renderEmployee } from './pages1.js';
import { renderAttendance, renderPayroll, renderReports, renderDeparted } from './pages2.js';
import { renderAdmin, renderSync } from './pages3.js';

let currentUser = null;
let serverStatus = null;
let currentRoute = '';

export function getCurrentUser() {
  return currentUser;
}

const NAV_ITEMS = [
  { id: '', label: 'Home', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { id: 'employees', label: 'All Staff', icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z' },
  { id: 'attendance', label: 'Attendance', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
  { id: 'payroll', label: 'Work Days', icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
  { id: 'reports', label: 'Reports', icon: 'M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
  { id: 'departed', label: 'Departed', icon: 'M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1' },
  { id: 'admin', label: 'Admin', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z' },
  { id: 'sync', label: 'Sync & Health', icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15' }
];

function svgIcon(pathD) {
  const ns = 'http://www.w3.org/2000/svg';
  const el = document.createElementNS(ns, 'svg');
  el.setAttribute('viewBox', '0 0 24 24');
  el.setAttribute('fill', 'none');
  el.setAttribute('stroke', 'currentColor');
  el.setAttribute('stroke-width', '2');
  el.setAttribute('stroke-linecap', 'round');
  el.setAttribute('stroke-linejoin', 'round');
  el.style.width = '18px';
  el.style.height = '18px';
  const p = document.createElementNS(ns, 'path');
  p.setAttribute('d', pathD);
  el.appendChild(p);
  return el;
}

async function init() {
  try {
    const [authStatus, boot] = await Promise.all([
      api.get('/auth/status'),
      api.get('/api/bootstrap').catch(() => null)
    ]);
    serverStatus = authStatus;
    if (boot) {
      window.__bootstrap = boot;
      if (boot.today) window.__serverToday = boot.today;
    }
    if (!authStatus.authenticated) {
      renderLogin(authStatus);
      return;
    }
    currentUser = authStatus;
    window.__currentUser = currentUser;
    renderAppShell();
    setupSSE();
    window.addEventListener('hashchange', handleRoute);
    handleRoute();
  } catch (err) {
    document.getElementById('app').innerHTML = `
      <div style="padding:3rem;text-align:center;font-family:sans-serif;">
        <h2 style="color:#dc2626;margin-bottom:0.5rem">Unable to connect to server</h2>
        <p style="color:#64748b;margin-bottom:1.5rem">Please verify the backend server is running on port 8000.</p>
        <button onclick="location.reload()" style="padding:0.6rem 1.2rem;background:#0f172a;color:#fff;border:none;border-radius:8px;font-weight:600;cursor:pointer">Retry</button>
      </div>`;
  }
}

function renderLogin(auth) {
  const root = document.getElementById('app');
  const isDev = auth.dev_auth;

  const content = h('div', { class: 'boot-screen', style: 'background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);' },
    h('div', { style: 'max-width:460px;width:100%;background:#ffffff;border-radius:16px;padding:2.25rem 2rem;color:#0f172a;text-align:left;box-shadow:0 20px 25px -5px rgba(0,0,0,0.3);' },
      h('div', { style: 'display:flex;align-items:center;gap:0.75rem;margin-bottom:1rem;' },
        h('div', { class: 'brand-icon', style: 'width:38px;height:38px;font-size:1.1rem;' }, 'SM'),
        h('div', {},
          h('h1', { style: 'font-size:1.45rem;font-family:var(--font-display);font-weight:700;margin:0;' }, 'Staff Manager'),
          h('div', { style: 'font-size:0.78rem;color:#64748b;' }, 'Unified Workforce & Attendance System')
        )
      ),
      h('p', { style: 'font-size:0.88rem;color:#475569;margin-bottom:1.25rem;line-height:1.45;' },
        'Secure operations hub connecting directly to your master Excel workbook. Manages daily attendance, staff roster verification, departures, and data health.'
      ),
      isDev ? h('div', { style: 'background:#fef3c7;border:1px solid #fde68a;border-radius:10px;padding:0.85rem 1rem;margin-bottom:1.5rem;' },
        h('div', { style: 'font-weight:700;font-size:0.85rem;color:#92400e;margin-bottom:0.25rem;' }, '⚠️ LOCAL DEVELOPMENT MODE'),
        h('div', { style: 'font-size:0.78rem;color:#b45309;line-height:1.4;' },
          'You are connected to an isolated test copy (' + (auth.source_label || 'test_workbook.xlsx') + '). Select a test role to explore administrative features.'
        )
      ) : h('div', { style: 'background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:0.85rem 1rem;margin-bottom:1.5rem;' },
        h('div', { style: 'font-weight:700;font-size:0.85rem;color:#1e40af;margin-bottom:0.25rem;' }, '🔒 Production Authentication'),
        h('div', { style: 'font-size:0.78rem;color:#1d4ed8;line-height:1.4;' },
          'Production security is active. Please authenticate using your registered Microsoft 365 organization credentials.'
        )
      ),
      isDev ? h('div', { style: 'display:flex;flex-direction:column;gap:0.65rem;' },
        h('button', {
          class: 'btn pri',
          style: 'width:100%;justify-content:center;',
          onclick: () => loginDev('admin')
        }, 'Test as Administrator (Full Access)'),
        h('button', {
          class: 'btn',
          style: 'width:100%;justify-content:center;',
          onclick: () => loginDev('editor')
        }, 'Test as Editor (Attendance & Records)'),
        h('button', {
          class: 'btn',
          style: 'width:100%;justify-content:center;background:#f8fafc;',
          onclick: () => loginDev('viewer')
        }, 'Test as Viewer (Read Only)')
      ) : h('div', {},
        h('a', {
          href: '/auth/login',
          class: 'btn pri',
          style: 'width:100%;justify-content:center;text-decoration:none;display:flex;'
        }, 'Sign in with Microsoft 365')
      ),
      h('div', { style: 'margin-top:1.5rem;padding-top:1rem;border-top:1px solid #e2e8f0;font-size:0.74rem;color:#94a3b8;text-align:center;' },
        'Financial Policy Guard Active · Zero Payable Calculations Inferred'
      )
    )
  );
  setKids(root, content);
}

async function loginDev(role) {
  try {
    await api.post('/auth/dev-login', { role });
    location.reload();
  } catch (err) {
    toast(err.message || 'Login failed', 'bad');
  }
}

async function logout() {
  await api.post('/auth/logout', {});
  location.reload();
}

function renderAppShell() {
  const root = document.getElementById('app');
  root.innerHTML = '';

  const shell = h('div', { class: 'shell' });

  // Sidebar (Desktop)
  const sidebar = h('aside', { class: 'side' },
    h('div', { class: 'brand' },
      h('div', { class: 'brand-icon' }, 'SM'),
      h('span', {}, 'Staff Manager')
    ),
    ...NAV_ITEMS.map(item => {
      const a = h('a', { class: 'nav', href: '#/' + item.id, id: 'nav-' + (item.id || 'home') },
        svgIcon(item.icon),
        h('span', {}, item.label)
      );
      return a;
    }),
    h('div', { class: 'who' },
      h('div', { class: 'who-user' }, currentUser.name || currentUser.email),
      h('div', { class: 'who-role' },
        h('span', { style: 'text-transform:capitalize;font-weight:600;' }, currentUser.role || 'User'),
        h('button', { class: 'logout-btn', onclick: logout }, 'Sign out')
      )
    )
  );

  // Main Outlet
  const main = h('main', { id: 'main-content' });

  // Mobile "More" Drawer Sheet
  const moreSheetBackdrop = h('div', { class: 'more-sheet-backdrop', onclick: closeMoreSheet });
  const moreSheet = h('div', { class: 'more-sheet' },
    h('div', { class: 'more-sheet-handle' }),
    h('div', { style: 'font-weight:700;font-size:0.95rem;margin-bottom:0.75rem;padding:0 0.5rem;color:var(--ink);' }, 'More Operational Views'),
    ...NAV_ITEMS.slice(4).map(item => h('a', {
      class: 'more-sheet-item',
      href: '#/' + item.id,
      id: 'msheet-' + item.id,
      onclick: closeMoreSheet
    }, svgIcon(item.icon), h('span', {}, item.label))),
    h('div', { style: 'border-top:1px solid var(--line);margin-top:0.75rem;padding-top:0.75rem;' },
      h('button', {
        class: 'more-sheet-item',
        style: 'width:100%;color:var(--bad);background:none;border:none;cursor:pointer;',
        onclick: () => { closeMoreSheet(); logout(); }
      }, svgIcon('M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1'), h('span', {}, 'Sign Out'))
    )
  );

  function openMoreSheet() {
    moreSheetBackdrop.classList.add('open');
    moreSheet.classList.add('open');
  }

  function closeMoreSheet() {
    moreSheetBackdrop.classList.remove('open');
    moreSheet.classList.remove('open');
  }

  // Mobile Bottom Nav with More ☰ action
  const bottomNav = h('nav', { class: 'bottom' },
    ...NAV_ITEMS.slice(0, 4).map(item => {
      const a = h('a', { class: 'bnav', href: '#/' + item.id, id: 'bnav-' + (item.id || 'home') },
        svgIcon(item.icon),
        h('span', {}, item.label)
      );
      return a;
    }),
    h('button', {
      class: 'bnav',
      id: 'bnav-more',
      type: 'button',
      onclick: (e) => {
        e.preventDefault();
        openMoreSheet();
      }
    },
      svgIcon('M4 6h16M4 12h16M4 18h16'),
      h('span', {}, 'More ☰')
    )
  );

  shell.appendChild(sidebar);
  shell.appendChild(main);
  shell.appendChild(bottomNav);
  shell.appendChild(moreSheetBackdrop);
  shell.appendChild(moreSheet);
  root.appendChild(shell);
}

function handleRoute() {
  const rawHash = location.hash.replace(/^#\/?/, '');
  const [pathPart, queryPart] = rawHash.split('?');
  const [base, ...parts] = (pathPart || '').split('/');
  currentRoute = base || '';

  // Update navigation link active states
  document.querySelectorAll('.side a.nav').forEach(el => {
    el.classList.toggle('on', el.getAttribute('href') === '#/' + (base || ''));
  });
  document.querySelectorAll('.bottom a.bnav').forEach(el => {
    el.classList.toggle('on', el.getAttribute('href') === '#/' + (base || ''));
  });
  const moreRoutes = ['reports', 'departed', 'admin', 'sync'];
  const moreBtn = document.getElementById('bnav-more');
  if (moreBtn) moreBtn.classList.toggle('on', moreRoutes.includes(base));

  const main = document.getElementById('main-content');
  if (!main) return;

  setKids(main, h('div', { style: 'padding:2rem;text-align:center;color:var(--mut)' }, 'Loading operational view…'));

  const parsedParams = new URLSearchParams(queryPart || '');
  const queryObj = Object.fromEntries(parsedParams.entries());

  if (base === '' || base === 'home') {
    renderHome(main, queryObj);
  } else if (base === 'employees') {
    renderEmployees(main, queryObj);
  } else if (base === 'employee') {
    renderEmployee(main, decodeURIComponent(parts[0] || ''));
  } else if (base === 'sheet' || base === 'sheets' || base === 'group' || base === 'groups') {
    const sheetName = decodeURIComponent(parts[0] || queryObj.sheet || queryObj.group || '');
    renderEmployees(main, { ...queryObj, sheet: sheetName });
  } else if (base === 'attendance') {
    renderAttendance(main, queryObj);
  } else if (base === 'payroll') {
    renderPayroll(main, queryObj);
  } else if (base === 'reports') {
    renderReports(main, queryObj);
  } else if (base === 'departed') {
    renderDeparted(main, queryObj);
  } else if (base === 'admin') {
    renderAdmin(main, queryObj);
  } else if (base === 'sync') {
    renderSync(main);
  } else {
    // If base is directly a sheet name (e.g. #/Babulal or #/Bhagwat)
    const decoded = decodeURIComponent(base);
    if (decoded && decoded !== '404') {
      renderEmployees(main, { ...queryObj, sheet: decoded });
    } else {
      setKids(main, h('div', { class: 'empty' },
        h('h2', {}, '404 — Page Not Found'),
        h('p', { class: 'sub' }, 'The requested view does not exist.'),
        h('a', { href: '#/', class: 'btn pri', style: 'margin-top:1rem;display:inline-flex;' }, 'Return Home')
      ));
    }
  }
}

function setupSSE() {
  try {
    const es = new EventSource('/api/events');
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'sync' || data.type === 'change') {
          // Subtle refresh without wiping form state
          if (document.visibilityState === 'visible') {
            const refreshBtn = document.getElementById('quick-refresh-btn');
            if (refreshBtn) refreshBtn.click();
          }
        }
      } catch (err) {}
    };
  } catch (err) {}
}

// Register service worker safely
if ('serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}

init();
