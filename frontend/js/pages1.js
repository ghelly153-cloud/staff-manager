// Pages: Home (Unified Overview), Employees (Consolidated Roster), Employee Profile Dossier.
import { api } from './api.js';
import { h, setKids, num, inr, fdate, today, badge, statCard, policySafeguard, empty, toast, modal, qs } from './ui.js';

export async function renderHome(main, query) {
  const date = query.date || sessionStorage.getItem('date') || today();
  sessionStorage.setItem('date', date);

  setKids(main, h('div', { style: 'padding:2rem;text-align:center;color:var(--mut)' }, 'Loading unified workforce metrics…'));

  try {
    const [dash, syncStatus] = await Promise.all([
      api.get(`/api/dashboard?date=${date}`),
      api.get('/api/sync/status')
    ]);

    const s = dash.summary;
    const att = s.attendance || {};
    const isLive = syncStatus.live;

    const content = h('div', {},
      // Top operational header
      h('div', { class: 'top' },
        h('div', { class: 'top-title' },
          h('h1', {}, 'Unified Workforce Operations'),
          h('div', { class: 'sub' }, `Consolidated management for all ${num(s.total)} staff members across all workbook sheets.`)
        ),
        h('div', { class: 'top-actions' },
          h('div', { style: 'display:flex;align-items:center;gap:0.4rem;background:#fff;border:1px solid var(--line);border-radius:var(--r-sm);padding:0.25rem 0.65rem;' },
            h('label', { style: 'margin:0;font-size:0.75rem;font-weight:600;' }, 'Date:'),
            h('input', {
              type: 'date',
              value: date,
              max: today(),
              style: 'border:none;min-height:auto;padding:0.2rem 0;font-size:0.85rem;background:transparent;cursor:pointer;',
              onchange: (e) => {
                location.hash = `#/?date=${e.target.value}`;
              }
            })
          ),
          h('button', {
            id: 'quick-refresh-btn',
            class: 'btn sm',
            title: 'Refresh from source workbook',
            onclick: async (e) => {
              e.target.disabled = true;
              try {
                await api.post('/api/sync/refresh', {});
                toast('Workbook refreshed', 'ok');
                renderHome(main, { date });
              } catch (err) {
                toast(err.message || 'Refresh failed', 'bad');
              } finally {
                e.target.disabled = false;
              }
            }
          }, '⟳ Refresh Source')
        )
      ),

      // Honest Source Freshness Banner
      h('div', {
        class: `banner ${isLive ? 'ok' : 'info'}`,
        style: 'justify-content:space-between;cursor:pointer;',
        onclick: () => { location.hash = '#/sync'; }
      },
        h('div', { style: 'display:flex;align-items:center;gap:0.65rem;' },
          h('span', { class: `dot ${syncStatus.state}` }),
          h('div', {},
            h('strong', {}, isLive ? 'Live Microsoft 365 Connected' : 'Local Test Copy (Isolated Development)'),
            h('span', { style: 'margin-left:0.5rem;font-size:0.82rem;opacity:0.85;' },
              `Source: ${syncStatus.source ? syncStatus.source.file : 'test_workbook.xlsx'} · Last sync: ${syncStatus.last_success ? syncStatus.last_success.split('T')[1].slice(0, 5) : 'Just now'}`
            )
          )
        ),
        h('span', { style: 'font-size:0.8rem;text-decoration:underline;' }, 'View Connection Health →')
      ),

      // Policy Safeguard
      policySafeguard(s.pay ? s.pay.policy_notice : null),

      // High Priority Workforce KPIs (Unified - No Group 1/2 categorization)
      h('div', { class: 'grid g4', style: 'margin-bottom:1.25rem;' },
        statCard('Total Staff Records', num(s.total), 'All sheets consolidated', 'primary'),
        statCard('Verified Active', num(s.active), s.not_verified > 0 ? `${num(s.not_verified)} awaiting review` : 'All records active in Excel', 'success'),
        statCard('Status Not Verified', num(s.not_verified), s.not_verified === 0 ? 'Zero pending reviews' : 'Requires confirmation', s.not_verified === 0 ? '' : 'warning'),
        statCard('Departed Staff', num(s.departed), 'Historical records preserved', 'danger')
      ),

      // Attendance Summary Card (Unified)
      h('div', { class: 'card', style: 'margin-bottom:1.25rem;' },
        h('div', { class: 'card-header' },
          h('h3', { class: 'card-title' }, `Daily Attendance Progress — ${fdate(date)}`),
          h('a', { href: `#/attendance?date=${date}`, class: 'btn sm pri' }, 'Open Daily Sheet →')
        ),
        h('div', { class: 'grid g3' },
          h('div', { style: 'background:var(--ok-bg);border:1px solid #bbf7d0;border-radius:var(--r-sm);padding:0.85rem 1rem;' },
            h('div', { style: 'font-size:0.8rem;font-weight:700;color:var(--ok);text-transform:uppercase;' }, 'Present Today'),
            h('div', { style: 'font-size:1.6rem;font-weight:700;color:var(--ok);' }, num(att.present || 0)),
            h('div', { style: 'font-size:0.75rem;color:#166534;' }, 'Explicitly marked present')
          ),
          h('div', { style: 'background:var(--bad-bg);border:1px solid #fecaca;border-radius:var(--r-sm);padding:0.85rem 1rem;' },
            h('div', { style: 'font-size:0.8rem;font-weight:700;color:var(--bad);text-transform:uppercase;' }, 'Absent Today'),
            h('div', { style: 'font-size:1.6rem;font-weight:700;color:var(--bad);' }, num(att.absent || 0)),
            h('div', { style: 'font-size:0.75rem;color:#991b1b;' }, 'Explicitly marked absent')
          ),
          h('div', { style: 'background:var(--grey-bg);border:1px solid var(--line);border-radius:var(--r-sm);padding:0.85rem 1rem;' },
            h('div', { style: 'font-size:0.8rem;font-weight:700;color:var(--mut);text-transform:uppercase;' }, 'Not Recorded'),
            h('div', { style: 'font-size:1.6rem;font-weight:700;color:var(--ink);' }, num(att.not_recorded || s.total)),
            h('div', { style: 'font-size:0.75rem;color:var(--mut);' }, 'Attendance pending for today')
          )
        )
      ),

      // Operational Workforce Sheets (Unified overview of master workbook sheets without dividing staff)
      h('div', { class: 'card', style: 'margin-bottom:1.25rem;' },
        h('div', { class: 'card-header' },
          h('h3', { class: 'card-title' }, 'Master Workbook Sheets & Distribution'),
          h('a', { href: '#/employees', class: 'btn sm' }, 'View All Staff →')
        ),
        h('div', { class: 'tw' },
          h('table', {},
            h('thead', {},
              h('tr', {},
                h('th', {}, 'Workbook Sheet'),
                h('th', { class: 'n' }, 'Staff Count'),
                h('th', { class: 'n' }, 'Recorded Legacy Days'),
                h('th', { class: 'n' }, 'Rates Authorized'),
                h('th', {}, 'Sheet Status'),
                h('th', { style: 'text-align:right;' }, 'Direct Actions')
              )
            ),
            h('tbody', {},
              ...(dash.groups || []).map(g => h('tr', {},
                h('td', { style: 'font-weight:600;' },
                  h('a', { href: `#/employees?sheet=${encodeURIComponent(g.name)}`, title: `View ${g.name} staff roster` }, g.name)
                ),
                h('td', { class: 'n' }, num(g.summary ? g.summary.total : 0)),
                h('td', { class: 'n' }, num(g.summary && g.summary.pay ? g.summary.pay.total_legacy_days : 0)),
                h('td', { class: 'n' }, badge('0 (Locked)', 'warn')),
                h('td', {}, badge('Integrated', 'teal')),
                h('td', { style: 'text-align:right;' },
                  h('div', { style: 'display:inline-flex;gap:0.35rem;' },
                    h('a', { href: `#/employees?sheet=${encodeURIComponent(g.name)}`, class: 'btn sm', style: 'padding:0.2rem 0.55rem;font-size:0.75rem;' }, 'Staff →'),
                    h('a', { href: `#/attendance?sheet=${encodeURIComponent(g.name)}`, class: 'btn sm teal', style: 'padding:0.2rem 0.55rem;font-size:0.75rem;' }, 'Attendance →')
                  )
                )
              ))
            )
          )
        )
      ),

      // Quick Operational Actions
      h('div', { class: 'grid g4' },
        h('a', { href: '#/attendance', class: 'card', style: 'text-decoration:none;display:block;border-left:4px solid var(--teal);' },
          h('div', { style: 'font-weight:700;font-size:1rem;color:var(--ink);margin-bottom:0.25rem;' }, 'Record Attendance'),
          h('div', { style: 'font-size:0.8rem;color:var(--mut);' }, 'Fast single-click attendance marking for all staff.')
        ),
        h('a', { href: '#/employees', class: 'card', style: 'text-decoration:none;display:block;border-left:4px solid var(--indigo);' },
          h('div', { style: 'font-weight:700;font-size:1rem;color:var(--ink);margin-bottom:0.25rem;' }, 'Staff Directory'),
          h('div', { style: 'font-size:0.8rem;color:var(--mut);' }, 'Search, filter, and inspect complete employee records.')
        ),
        h('a', { href: '#/admin?tab=review', class: 'card', style: 'text-decoration:none;display:block;border-left:4px solid var(--warn);' },
          h('div', { style: 'font-weight:700;font-size:1rem;color:var(--ink);margin-bottom:0.25rem;' }, 'Status Review'),
          h('div', { style: 'font-size:0.8rem;color:var(--mut);' }, `Verify ${num(s.not_verified)} unconfirmed employee records.`)
        ),
        h('a', { href: '#/reports', class: 'card', style: 'text-decoration:none;display:block;border-left:4px solid var(--ok);' },
          h('div', { style: 'font-weight:700;font-size:1rem;color:var(--ink);margin-bottom:0.25rem;' }, 'Export Reports'),
          h('div', { style: 'font-size:0.8rem;color:var(--mut);' }, 'Download clean CSV/Excel exports with masked PII.')
        )
      )
    );

    setKids(main, content);
  } catch (err) {
    setKids(main, empty('Error loading dashboard', err.message, '⚠️'));
  }
}

export async function renderEmployees(main, query) {
  const f = {
    q: query.q || '',
    status: query.status || 'current',
    sheet: query.sheet || query.group || '',
    location: query.location || '',
    designation: query.designation || '',
    sort: query.sort || 'name',
    dir: query.dir || 'asc',
    page: parseInt(query.page || '1', 10),
    page_size: 30
  };

  setKids(main, h('div', { style: 'padding:2rem;text-align:center;color:var(--mut)' }, 'Loading unified staff roster…'));

  try {
    const [empData, bootstrap] = await Promise.all([
      api.get(`/api/employees?${qs({
        q: f.q,
        status: f.status,
        group: f.sheet,
        location: f.location,
        designation: f.designation,
        sort: f.sort,
        dir: f.dir,
        page: f.page,
        page_size: f.page_size
      })}`),
      api.get('/api/bootstrap')
    ]);

    const userRole = bootstrap.role || (window.__currentUser && window.__currentUser.role) || 'viewer';
    const canEdit = userRole === 'admin' || userRole === 'editor';
    const sheets = bootstrap.groups || [];
    const locations = bootstrap.locations || [];
    const designations = bootstrap.designations || [];

    const navTo = (updates) => {
      const merged = { ...f, ...updates, page: updates.page || 1 };
      location.hash = `#/employees?${qs({
        q: merged.q,
        status: merged.status,
        sheet: merged.sheet,
        location: merged.location,
        designation: merged.designation,
        sort: merged.sort,
        page: merged.page
      })}`;
    };

    const content = h('div', {},
      // Top bar
      h('div', { class: 'top' },
        h('div', { class: 'top-title' },
          h('h1', {}, 'All Staff & Employees'),
          h('div', { class: 'sub' }, `Showing ${empData.items ? empData.items.length : 0} of ${num(empData.total)} total records across all sheets.`)
        ),
        h('div', { class: 'top-actions' },
          canEdit ? h('button', {
            class: 'btn pri',
            onclick: () => openAddEmployeeModal(bootstrap, () => renderEmployees(main, query))
          }, '+ Add Employee') : null
        )
      ),

      // Filter Bar
      h('div', { class: 'filter-bar' },
        h('div', { class: 'filters-grid' },
          h('div', {},
            h('label', {}, 'Search Name or ID'),
            h('input', {
              type: 'search',
              placeholder: 'Type name, ID, or location…',
              value: f.q,
              onkeydown: (e) => { if (e.key === 'Enter') navTo({ q: e.target.value }); }
            })
          ),
          h('div', {},
            h('label', {}, 'Source Sheet (Workbook)'),
            h('select', { onchange: (e) => navTo({ sheet: e.target.value }) },
              h('option', { value: '' }, 'All Sheets (Consolidated)'),
              ...sheets.map(sh => h('option', { value: sh, selected: sh === f.sheet }, sh))
            )
          ),
          h('div', {},
            h('label', {}, 'Location'),
            h('select', { onchange: (e) => navTo({ location: e.target.value }) },
              h('option', { value: '' }, 'All Locations'),
              ...locations.map(loc => h('option', { value: loc, selected: loc === f.location }, loc))
            )
          ),
          h('div', {},
            h('label', {}, 'Sort Order'),
            h('select', { onchange: (e) => navTo({ sort: e.target.value }) },
              h('option', { value: 'name', selected: f.sort === 'name' }, 'Employee Name (A-Z)'),
              h('option', { value: 'row', selected: f.sort === 'row' }, 'Workbook Sheet Order'),
              h('option', { value: 'location', selected: f.sort === 'location' }, 'Location'),
              h('option', { value: 'status', selected: f.sort === 'status' }, 'Employment Status')
            )
          )
        ),
        // Filter Chips for Quick Status Selection
        h('div', { class: 'filter-chips' },
          ...[
            ['current', 'Active & Unverified (Current)'],
            ['all', 'All Records (Inc. Departed)'],
            ['Active', 'Verified Active Only'],
            ['Not Verified', 'Not Verified (Needs Review)'],
            ['Departed', 'Departed Only']
          ].map(([val, label]) => h('div', {
            class: `filter-chip ${f.status === val ? 'active' : ''}`,
            onclick: () => navTo({ status: val })
          }, label)),
          (f.q || f.sheet || f.location || f.status !== 'current') ? h('div', {
            class: 'filter-chip',
            style: 'background:#fee2e2;color:#991b1b;border-color:#fecaca;',
            onclick: () => navTo({ q: '', sheet: '', location: '', designation: '', status: 'current' })
          }, '✕ Reset Filters') : null
        )
      ),

      // Employee Table & Mobile Cards Container
      empData.items && empData.items.length > 0 ? h('div', { class: 'tw resp' },
        // Desktop Table
        h('table', {},
          h('thead', {},
            h('tr', {},
              h('th', {}, 'Employee Name'),
              h('th', {}, 'Source Sheet'),
              h('th', {}, 'Designation'),
              h('th', {}, 'Location'),
              h('th', {}, 'Employment Status'),
              h('th', { class: 'n' }, 'Recorded Days'),
              h('th', { class: 'n' }, 'Source Rate'),
              h('th', {}, 'Compensation Policy')
            )
          ),
          h('tbody', {},
            ...empData.items.map(r => h('tr', {},
              h('td', { style: 'font-weight:600;' },
                h('a', { href: `#/employee/${encodeURIComponent(r.ref)}` }, r.name),
                r.id ? h('div', { style: 'font-size:0.75rem;color:var(--mut);font-weight:400;' }, r.id) : null
              ),
              h('td', {}, badge(r.group || 'Sheet', 'grey')),
              h('td', {}, r.designation || h('span', { style: 'color:var(--mut);' }, '—')),
              h('td', {}, r.location || h('span', { style: 'color:var(--mut);' }, '—')),
              h('td', {},
                r.status === 'Active' ? badge('Active', 'ok') :
                r.status === 'Departed' ? badge('Departed', 'bad') :
                badge('Not Verified', 'warn')
              ),
              h('td', { class: 'n' }, num(r.legacy_days || 0)),
              h('td', { class: 'n' }, r.rate ? inr(r.rate) : '—'),
              h('td', {}, badge('Unapproved', 'indigo'))
            ))
          )
        ),

        // Mobile Cards Alternative
        h('div', { class: 'ecards' },
          ...empData.items.map(r => h('div', { class: 'ecard' },
            h('div', { class: 'ecard-top' },
              h('a', { class: 'ecard-name', href: `#/employee/${encodeURIComponent(r.ref)}` }, r.name),
              r.status === 'Active' ? badge('Active', 'ok') :
              r.status === 'Departed' ? badge('Departed', 'bad') :
              badge('Not Verified', 'warn')
            ),
            h('div', { class: 'ecard-meta' }, `${r.group || 'Sheet'} · ${r.designation || 'Staff'} · ${r.location || 'Location unassigned'}`),
            h('div', { class: 'ecard-details' },
              h('div', { class: 'dt' }, 'Permanent ID:'),
              h('div', { class: 'dd' }, r.id || 'Pending setup'),
              h('div', { class: 'dt' }, 'Recorded Days:'),
              h('div', { class: 'dd' }, num(r.legacy_days || 0)),
              h('div', { class: 'dt' }, 'Compensation:'),
              h('div', { class: 'dd' }, 'Unapproved Rate')
            ),
            h('div', { style: 'display:flex;justify-content:flex-end;' },
              h('a', { href: `#/employee/${encodeURIComponent(r.ref)}`, class: 'btn sm' }, 'View Profile Dossier →')
            )
          ))
        )
      ) : empty('No staff found', 'Try adjusting your search query or filters to find employees.', '🔍'),

      // Pagination
      empData.total_pages > 1 ? h('div', { style: 'display:flex;justify-content:center;gap:0.5rem;margin-top:1.5rem;' },
        h('button', {
          class: 'btn sm',
          disabled: f.page <= 1,
          onclick: () => navTo({ page: f.page - 1 })
        }, '‹ Previous'),
        h('span', { style: 'display:flex;align-items:center;font-size:0.85rem;color:var(--mut);padding:0 0.5rem;' },
          `Page ${f.page} of ${empData.total_pages}`
        ),
        h('button', {
          class: 'btn sm',
          disabled: f.page >= empData.total_pages,
          onclick: () => navTo({ page: f.page + 1 })
        }, 'Next ›')
      ) : null
    );

    setKids(main, content);
  } catch (err) {
    setKids(main, empty('Error loading staff', err.message, '⚠️'));
  }
}

export async function renderEmployee(main, ref) {
  setKids(main, h('div', { style: 'padding:2rem;text-align:center;color:var(--mut)' }, 'Loading employee dossier…'));

  try {
    const [emp, bootstrap] = await Promise.all([
      api.get(`/api/employees/${encodeURIComponent(ref)}`),
      api.get('/api/bootstrap')
    ]);

    const userRole = bootstrap.role || (window.__currentUser && window.__currentUser.role) || 'viewer';
    const canEdit = userRole === 'admin' || userRole === 'editor';
    const isAdmin = userRole === 'admin';

    const content = h('div', {},
      // Back navigation & Header
      h('div', { style: 'margin-bottom:0.75rem;' },
        h('a', { href: '#/employees', style: 'font-size:0.85rem;color:var(--mut);' }, '← Back to All Staff')
      ),
      h('div', { class: 'top' },
        h('div', { class: 'top-title' },
          h('h1', {}, emp.name),
          h('div', { class: 'sub' }, `Source: Sheet `, h('a', { href: `#/employees?sheet=${encodeURIComponent(emp.group)}` }, emp.group), `, Row ${emp.source ? emp.source.row : '—'}`)
        ),
        h('div', { class: 'top-actions' },
          emp.status === 'Active' ? badge('Active', 'ok') :
          emp.status === 'Departed' ? badge('Departed', 'bad') :
          badge('Status Not Verified', 'warn'),
          canEdit ? h('button', {
            class: 'btn pri sm',
            onclick: () => openEditEmployeeModal(emp, bootstrap, () => renderEmployee(main, ref))
          }, 'Edit Record') : null
        )
      ),

      // Policy Safeguard Notice
      policySafeguard('This employee record does not have an approved compensation rate. Any displayed spreadsheet numbers are raw source values preserved for provenance and cannot be paid or owed.'),

      // Profile Details Grid
      h('div', { class: 'grid g2', style: 'margin-bottom:1.5rem;' },
        // Identity & Core Details
        h('div', { class: 'card' },
          h('div', { class: 'card-header' },
            h('h3', { class: 'card-title' }, 'Identity & Workbook Provenance')
          ),
          h('table', {},
            h('tbody', {},
              h('tr', {}, h('td', { style: 'color:var(--mut);width:140px;' }, 'Permanent ID'), h('td', { style: 'font-weight:600;' }, emp.id || badge('Pending Setup', 'grey'))),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Source Sheet'), h('td', {}, h('a', { href: `#/employees?sheet=${encodeURIComponent(emp.group)}` }, emp.group))),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Workbook Row'), h('td', {}, emp.source ? emp.source.row : '—')),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Designation'), h('td', {}, emp.designation || 'Not specified')),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Location'), h('td', {}, emp.location || 'Not specified')),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Mobile Phone'), h('td', {},
                emp.mobile ? h('span', {}, emp.mobile) : h('span', { style: 'color:var(--mut);' }, 'Not on file')
              )),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Aadhaar / Gov ID'), h('td', {},
                emp.aadhaar ? h('span', {}, emp.aadhaar) : h('span', { style: 'color:var(--mut);' }, 'Not on file')
              ))
            )
          )
        ),

        // Attendance & Work Days Summary
        h('div', { class: 'card' },
          h('div', { class: 'card-header' },
            h('h3', { class: 'card-title' }, 'Operational Work Days')
          ),
          h('table', {},
            h('tbody', {},
              h('tr', {}, h('td', { style: 'color:var(--mut);width:180px;' }, 'Legacy Sept Days'), h('td', { class: 'n', style: 'font-weight:600;' }, num(emp.sept ? emp.sept.value : 0))),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Legacy Oct Days'), h('td', { class: 'n', style: 'font-weight:600;' }, num(emp.octo ? emp.octo.value : 0))),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Date-wise Days'), h('td', { class: 'n', style: 'font-weight:600;' }, num(emp.datewise_days || 0))),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Raw Spreadsheet Rate'), h('td', { class: 'n' }, emp.rate ? inr(emp.rate.value) : '—')),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Approved Amount'), h('td', { class: 'n' }, badge('₹0.00 (Unapproved)', 'indigo'))),
              h('tr', {}, h('td', { style: 'color:var(--mut);' }, 'Departure Date'), h('td', {}, emp.dep_date ? fdate(emp.dep_date) : 'Active staff member'))
            )
          )
        )
      )
    );

    setKids(main, content);
  } catch (err) {
    setKids(main, empty('Error loading employee', err.message, '⚠️'));
  }
}

function openAddEmployeeModal(bootstrap, onSuccess) {
  const v = {
    group: (bootstrap.groups || [])[0] || 'Babulal',
    name: '',
    designation: '',
    location: '',
    mobile: ''
  };

  const body = h('div', { class: 'filters-grid', style: 'grid-template-columns:1fr;gap:0.75rem;' },
    h('div', {},
      h('label', {}, 'Destination Sheet *'),
      h('select', { onchange: (e) => v.group = e.target.value },
        ...(bootstrap.groups || []).map(g => h('option', { value: g }, g))
      )
    ),
    h('div', {},
      h('label', {}, 'Full Staff Name *'),
      h('input', {
        type: 'text',
        placeholder: 'Enter full name',
        oninput: (e) => v.name = e.target.value
      })
    ),
    h('div', {},
      h('label', {}, 'Designation'),
      h('input', {
        type: 'text',
        placeholder: 'e.g. Karigar, Helper, Supervisor',
        oninput: (e) => v.designation = e.target.value
      })
    ),
    h('div', {},
      h('label', {}, 'Location'),
      h('select', { onchange: (e) => v.location = e.target.value },
        h('option', { value: '' }, 'Select location (optional)'),
        ...(bootstrap.locations || []).map(l => h('option', { value: l }, l))
      )
    ),
    h('div', {},
      h('label', {}, 'Mobile Number (10 digits)'),
      h('input', {
        type: 'tel',
        placeholder: 'e.g. 9876543210',
        oninput: (e) => v.mobile = e.target.value
      })
    )
  );

  modal('Add Staff Record', body, async () => {
    if (!v.name.trim()) {
      toast('Employee name is required', 'bad');
      return false;
    }
    try {
      await api.post('/api/employees', { data: v });
      toast('Employee created successfully', 'ok');
      onSuccess();
      return true;
    } catch (err) {
      toast(err.message || 'Failed to add employee', 'bad');
      return false;
    }
  }, 'Add Employee');
}

function openEditEmployeeModal(emp, bootstrap, onSuccess) {
  const v = {
    name: emp.name,
    designation: emp.designation || '',
    location: emp.location || '',
    status: emp.status || 'Not Verified'
  };

  const body = h('div', { class: 'filters-grid', style: 'grid-template-columns:1fr;gap:0.75rem;' },
    h('div', {},
      h('label', {}, 'Full Name *'),
      h('input', {
        type: 'text',
        value: v.name,
        oninput: (e) => v.name = e.target.value
      })
    ),
    h('div', {},
      h('label', {}, 'Designation'),
      h('input', {
        type: 'text',
        value: v.designation,
        oninput: (e) => v.designation = e.target.value
      })
    ),
    h('div', {},
      h('label', {}, 'Location'),
      h('select', { onchange: (e) => v.location = e.target.value },
        h('option', { value: '' }, 'Select location'),
        ...(bootstrap.locations || []).map(l => h('option', { value: l, selected: l === v.location }, l))
      )
    ),
    h('div', {},
      h('label', {}, 'Employment Status'),
      h('select', { onchange: (e) => v.status = e.target.value },
        h('option', { value: 'Not Verified', selected: v.status === 'Not Verified' }, 'Not Verified (Pending verification)'),
        h('option', { value: 'Active', selected: v.status === 'Active' }, 'Active'),
        h('option', { value: 'Departed', selected: v.status === 'Departed' }, 'Departed')
      )
    )
  );

  modal('Edit Staff Record', body, async () => {
    if (!v.name.trim()) {
      toast('Name cannot be empty', 'bad');
      return false;
    }
    try {
      await api.put(`/api/employees/${encodeURIComponent(emp.ref)}`, { data: v });
      toast('Employee record saved', 'ok');
      onSuccess();
      return true;
    } catch (err) {
      toast(err.message || 'Failed to save changes', 'bad');
      return false;
    }
  }, 'Save Changes');
}
