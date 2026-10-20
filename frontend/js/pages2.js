// Pages: Attendance (Sheet-Wise Daily Operations), Work Records (No Payment Obligations), Reports & Exports, Smart Departed Management.
import { api } from './api.js';
import { h, setKids, num, inr, fdate, today, badge, policySafeguard, empty, toast, confirmBox, modal, qs } from './ui.js';

export async function renderAttendance(main, query) {
  const date = query.date || sessionStorage.getItem('date') || today();
  sessionStorage.setItem('date', date);

  const f = {
    date,
    sheet: query.sheet || '',
    location: query.location || '',
    statusFilter: query.statusFilter || '',
    q: (query.q || '').toLowerCase()
  };

  setKids(main, h('div', { style: 'padding:2rem;text-align:center;color:var(--mut)' }, 'Loading daily attendance roster…'));

  try {
    const [attData, bootstrap] = await Promise.all([
      api.get(`/api/attendance?date=${f.date}&include_departed=true`),
      api.get('/api/bootstrap')
    ]);

    const userRole = bootstrap.role || (window.__currentUser && window.__currentUser.role) || 'viewer';
    const canEdit = userRole === 'admin' || userRole === 'editor';
    const sheets = bootstrap.groups || [];
    const locations = bootstrap.locations || [];
    const items = attData.items || [];

    // Filter items
    const filtered = items.filter(r => {
      if (f.sheet && r.group !== f.sheet) return false;
      if (f.location && r.location !== f.location) return false;
      if (f.q && !r.name.toLowerCase().includes(f.q)) return false;
      if (f.statusFilter === 'present' && (r.status === 'Departed' || r.att !== 'Present')) return false;
      if (f.statusFilter === 'absent' && (r.status === 'Departed' || r.att !== 'Absent')) return false;
      if (f.statusFilter === 'departed' && r.status !== 'Departed') return false;
      if (f.statusFilter === 'pending' && (r.status === 'Departed' || (r.att && r.att !== 'Not Recorded'))) return false;
      return true;
    });

    // Counts for sheet/filtered scope
    const scopedItems = f.sheet ? items.filter(r => r.group === f.sheet) : items;
    const presentCount = scopedItems.filter(r => r.status !== 'Departed' && r.att === 'Present').length;
    const absentCount = scopedItems.filter(r => r.status !== 'Departed' && r.att === 'Absent').length;
    const departedCount = scopedItems.filter(r => r.status === 'Departed').length;
    const notRecordedCount = scopedItems.filter(r => r.status !== 'Departed' && (!r.att || r.att === 'Not Recorded')).length;

    // Counts per sheet for the sheet-wise tabs
    const sheetCounts = {};
    for (const sh of sheets) {
      sheetCounts[sh] = items.filter(r => r.group === sh).length;
    }

    const navTo = (updates) => {
      const merged = { ...f, ...updates };
      location.hash = `#/attendance?${qs({
        date: merged.date,
        sheet: merged.sheet,
        location: merged.location,
        statusFilter: merged.statusFilter,
        q: merged.q
      })}`;
    };

    const refreshKPIs = () => {
      const scoped = f.sheet ? items.filter(r => r.group === f.sheet) : items;
      const p = scoped.filter(r => r.status !== 'Departed' && r.att === 'Present').length;
      const a = scoped.filter(r => r.status !== 'Departed' && r.att === 'Absent').length;
      const d = scoped.filter(r => r.status === 'Departed').length;
      const pend = scoped.filter(r => r.status !== 'Departed' && (!r.att || r.att === 'Not Recorded')).length;

      const elP = document.getElementById('kpi-att-present');
      if (elP) elP.textContent = num(p);
      const elA = document.getElementById('kpi-att-absent');
      if (elA) elA.textContent = num(a);
      const elD = document.getElementById('kpi-att-departed');
      if (elD) elD.textContent = num(d);
      const elPend = document.getElementById('kpi-att-pending');
      if (elPend) elPend.textContent = num(pend);
    };

    const updateRowAndCardDom = (r) => {
      const isDep = r.status === 'Departed';
      const curAtt = r.att || 'Not Recorded';
      const safeId = r.ref.replace(/[^a-zA-Z0-9_-]/g, '_');

      // Update Desktop Table Row
      const tr = document.getElementById(`att-row-${safeId}`);
      if (tr) {
        const statusCell = tr.querySelector('.status-cell');
        if (statusCell) {
          setKids(statusCell,
            isDep ? badge('Departed', 'warn') :
            curAtt === 'Present' ? badge('Present', 'ok') :
            curAtt === 'Absent' ? badge('Absent', 'bad') :
            badge('Not Recorded', 'grey')
          );
        }
        const btnPresent = tr.querySelector('.btn-att-present');
        if (btnPresent) btnPresent.className = `btn-att-present ${!isDep && curAtt === 'Present' ? 'on Present' : ''}`;
        const btnAbsent = tr.querySelector('.btn-att-absent');
        if (btnAbsent) btnAbsent.className = `btn-att-absent ${!isDep && curAtt === 'Absent' ? 'on Absent' : ''}`;
        const btnDeparted = tr.querySelector('.btn-att-departed');
        if (btnDeparted) btnDeparted.className = `btn-att-departed ${isDep ? 'on Departed' : ''}`;
        const btnReset = tr.querySelector('.btn-att-reset');
        if (btnReset) btnReset.style.display = (!isDep && curAtt !== 'Not Recorded' && canEdit) ? 'inline-flex' : 'none';
      }

      // Update Mobile Card
      const card = document.getElementById(`att-card-${safeId}`);
      if (card) {
        const statusBadge = card.querySelector('.ecard-status-badge');
        if (statusBadge) {
          setKids(statusBadge,
            isDep ? badge('Departed', 'warn') :
            curAtt === 'Present' ? badge('Present', 'ok') :
            curAtt === 'Absent' ? badge('Absent', 'bad') :
            badge('Not Recorded', 'grey')
          );
        }
        const mBtnP = card.querySelector('.mbtn-present');
        if (mBtnP) mBtnP.className = `btn sm mbtn-present ${!isDep && curAtt === 'Present' ? 'teal' : ''}`;
        const mBtnA = card.querySelector('.mbtn-absent');
        if (mBtnA) mBtnA.className = `btn sm mbtn-absent ${!isDep && curAtt === 'Absent' ? 'dng' : ''}`;
        const mBtnD = card.querySelector('.mbtn-departed');
        if (mBtnD) mBtnD.className = `btn sm mbtn-departed ${isDep ? 'warn' : ''}`;
        const mBtnReset = card.querySelector('.mbtn-reset');
        if (mBtnReset) mBtnReset.style.display = (!isDep && curAtt !== 'Not Recorded' && canEdit) ? 'inline-flex' : 'none';
      }
    };

    const updateStatus = async (r, newStatus, btn) => {
      const prevAtt = r.att;
      const prevStatus = r.status;

      // 1. INSTANT OPTIMISTIC FEEDBACK (0 ms)
      r.att = newStatus;
      updateRowAndCardDom(r);
      refreshKPIs();
      if (btn) btn.classList.add('saving');

      try {
        const res = await api.post(`/api/attendance/${encodeURIComponent(r.ref)}`, {
          date: f.date,
          status: newStatus
        });
        if (res && (res.ok || res.saved != null)) {
          if (btn) btn.classList.remove('saving');
        } else {
          // Revert if rejected
          r.att = prevAtt;
          r.status = prevStatus;
          updateRowAndCardDom(r);
          refreshKPIs();
          toast((res && res.error) || 'Failed to save attendance', 'bad');
        }
      } catch (err) {
        // Revert on network failure
        r.att = prevAtt;
        r.status = prevStatus;
        updateRowAndCardDom(r);
        refreshKPIs();
        toast(err.message || 'Failed to update attendance', 'bad');
      } finally {
        if (btn) btn.classList.remove('saving');
      }
    };

    const markStaffPresent = async (r, btn) => {
      if (r.status === 'Departed') {
        const ok = await confirmBox(
          'Reactivate Departed Employee',
          `Restore ${r.name} to Active employee status and mark Present for ${fdate(f.date)}?`
        );
        if (!ok) return;
        const prevStatus = r.status;
        const prevAtt = r.att;
        r.status = 'Active';
        r.att = 'Present';
        updateRowAndCardDom(r);
        refreshKPIs();
        if (btn) btn.classList.add('saving');
        try {
          await api.post(`/api/status/${encodeURIComponent(r.ref)}`, { status: 'Active' });
          await api.post(`/api/attendance/${encodeURIComponent(r.ref)}`, { date: f.date, status: 'Present' });
          toast(`${r.name} reinstated and marked Present!`, 'ok');
        } catch (err) {
          r.status = prevStatus;
          r.att = prevAtt;
          updateRowAndCardDom(r);
          refreshKPIs();
          toast(err.message || 'Action failed', 'bad');
        } finally {
          if (btn) btn.classList.remove('saving');
        }
      } else {
        updateStatus(r, 'Present', btn);
      }
    };

    const markStaffAbsent = async (r, btn) => {
      if (r.status === 'Departed') {
        const ok = await confirmBox(
          'Reactivate Departed Employee',
          `Restore ${r.name} to Active employee status and mark Absent for ${fdate(f.date)}?`
        );
        if (!ok) return;
        const prevStatus = r.status;
        const prevAtt = r.att;
        r.status = 'Active';
        r.att = 'Absent';
        updateRowAndCardDom(r);
        refreshKPIs();
        if (btn) btn.classList.add('saving');
        try {
          await api.post(`/api/status/${encodeURIComponent(r.ref)}`, { status: 'Active' });
          await api.post(`/api/attendance/${encodeURIComponent(r.ref)}`, { date: f.date, status: 'Absent' });
          toast(`${r.name} reinstated and marked Absent!`, 'ok');
        } catch (err) {
          r.status = prevStatus;
          r.att = prevAtt;
          updateRowAndCardDom(r);
          refreshKPIs();
          toast(err.message || 'Action failed', 'bad');
        } finally {
          if (btn) btn.classList.remove('saving');
        }
      } else {
        updateStatus(r, 'Absent', btn);
      }
    };

    const markStaffDeparted = async (r, btn) => {
      if (r.status === 'Departed') {
        toast(`${r.name} is currently recorded as Departed. Use Present or Absent to reinstate.`, 'info');
        return;
      }
      let depDate = f.date || today();
      let depReason = 'Resigned';
      let notes = '';

      const form = h('div', { class: 'filters-grid', style: 'grid-template-columns:1fr;gap:0.75rem;' },
        h('p', { style: 'font-size:0.88rem;color:var(--mut);margin:0;' }, `Record confirmed departure for: ${r.name} (${r.group || 'Sheet'})`),
        h('div', {},
          h('label', {}, 'Confirmed Departure Date *'),
          h('input', {
            type: 'date',
            value: depDate,
            max: today(),
            onchange: (e) => depDate = e.target.value
          })
        ),
        h('div', {},
          h('label', {}, 'Reason for Departure'),
          h('select', { onchange: (e) => depReason = e.target.value },
            h('option', { value: 'Resigned' }, 'Resigned (Voluntary)'),
            h('option', { value: 'Contract Completed' }, 'Contract Completed'),
            h('option', { value: 'Seasonal Exit' }, 'Seasonal Exit (Post-Festival)'),
            h('option', { value: 'Relocated' }, 'Relocated to hometown'),
            h('option', { value: 'Health / Personal' }, 'Health / Family reasons'),
            h('option', { value: 'Other' }, 'Other')
          )
        ),
        h('div', {},
          h('label', {}, 'Operational Notes (Preserves Historical Logs)'),
          h('textarea', {
            rows: 2,
            placeholder: 'e.g. Handover completed, equipment returned…',
            oninput: (e) => notes = e.target.value
          })
        )
      );

      modal(`Record Staff Departure — ${r.name}`, form, async () => {
        if (!depDate) {
          toast('Departure date is required', 'bad');
          return false;
        }
        const prevStatus = r.status;
        r.status = 'Departed';
        updateRowAndCardDom(r);
        refreshKPIs();
        try {
          await api.post(`/api/status/${encodeURIComponent(r.ref)}`, {
            status: 'Departed',
            dep_date: depDate,
            reason: notes ? `${depReason}: ${notes}` : depReason
          });
          toast(`${r.name} marked as Departed`, 'ok');
          return true;
        } catch (err) {
          r.status = prevStatus;
          updateRowAndCardDom(r);
          refreshKPIs();
          toast(err.message || 'Failed to record departure', 'bad');
          return false;
        }
      }, 'Confirm Departure');
    };

    const markSheetAllPresent = async (targetSheet) => {
      const targetItems = targetSheet ? items.filter(r => r.group === targetSheet) : filtered;
      const unrecorded = targetItems.filter(r => r.status !== 'Departed' && (!r.att || r.att === 'Not Recorded'));
      if (unrecorded.length === 0) {
        toast(`All active staff in ${targetSheet || 'current view'} are already recorded!`, 'ok');
        return;
      }
      const ok = await confirmBox(
        'Sheet Attendance Confirmation',
        `Mark all ${unrecorded.length} active unrecorded staff in "${targetSheet || 'current view'}" as Present for ${fdate(f.date)}?`
      );
      if (!ok) return;

      try {
        await api.post('/api/attendance/bulk', {
          date: f.date,
          status: 'Present',
          refs: unrecorded.map(r => r.ref)
        });
        toast(`Marked ${unrecorded.length} staff as Present in ${targetSheet || 'sheet'}!`, 'ok');
        renderAttendance(main, query);
      } catch (err) {
        toast(err.message || 'Bulk update failed', 'bad');
      }
    };

    const clearSheetAttendance = async (targetSheet) => {
      const targetItems = targetSheet ? items.filter(r => r.group === targetSheet) : filtered;
      const recorded = targetItems.filter(r => r.att && r.att !== 'Not Recorded');
      if (recorded.length === 0) {
        toast('No attendance records to reset in this sheet', 'ok');
        return;
      }
      const ok = await confirmBox(
        'Reset Sheet Attendance',
        `Reset all ${recorded.length} daily attendance records in "${targetSheet || 'view'}" back to Not Recorded for ${fdate(f.date)}?`
      );
      if (!ok) return;

      try {
        await api.post('/api/attendance/bulk', {
          date: f.date,
          status: 'Not Recorded',
          refs: recorded.map(r => r.ref)
        });
        toast(`Reset ${recorded.length} attendance records`, 'ok');
        renderAttendance(main, query);
      } catch (err) {
        toast(err.message || 'Reset failed', 'bad');
      }
    };

    // Group filtered items by sheet for convenient sectioning
    const groupedBySheet = {};
    for (const item of filtered) {
      const sh = item.group || 'Other';
      if (!groupedBySheet[sh]) groupedBySheet[sh] = [];
      groupedBySheet[sh].push(item);
    }

    const content = h('div', {},
      // Top header
      h('div', { class: 'top' },
        h('div', { class: 'top-title' },
          h('h1', {}, `Daily Attendance — ${fdate(f.date)}`),
          h('div', { class: 'sub' }, `Convenient sheet-wise operations with Present, Absent, and Departed status tracking across ${sheets.length} sheets.`)
        ),
        h('div', { class: 'top-actions' },
          h('div', { style: 'display:flex;align-items:center;gap:0.4rem;background:#fff;border:1px solid var(--line);border-radius:var(--r-sm);padding:0.25rem 0.65rem;' },
            h('label', { style: 'margin:0;font-size:0.75rem;font-weight:600;' }, 'Date:'),
            h('input', {
              type: 'date',
              value: f.date,
              max: today(),
              style: 'border:none;min-height:auto;padding:0.2rem 0;font-size:0.85rem;background:transparent;cursor:pointer;',
              onchange: (e) => navTo({ date: e.target.value })
            })
          ),
          canEdit ? h('button', {
            class: 'btn sm teal',
            onclick: () => markSheetAllPresent(f.sheet)
          }, f.sheet ? `✓ Mark All Active in ${f.sheet} Present` : `✓ Mark All ${notRecordedCount} Unrecorded Present`) : null
        )
      ),

      // Date Mode Banners
      f.date !== today() ? h('div', { class: 'banner info', style: 'margin-bottom:1rem;display:flex;align-items:center;gap:0.65rem;' },
        h('div', {},
          h('strong', {}, `📅 Historical Attendance Mode: ${fdate(f.date)}`),
          h('div', { style: 'font-size:0.82rem;margin-top:0.2rem;' },
            `You are viewing saved historical records for ${fdate(f.date)}. Past attendance is safely retrieved from persistent storage. Changes made here persist specifically for this date without altering current or other dates.`
          )
        )
      ) : null,

      !attData.has_any_records ? h('div', { class: 'banner warn', style: 'margin-bottom:1rem;display:flex;align-items:center;gap:0.65rem;' },
        h('div', {},
          h('strong', {}, `No Attendance Recorded for ${fdate(f.date)}`),
          h('div', { style: 'font-size:0.82rem;margin-top:0.2rem;' },
            `No attendance has been saved for this date yet. Select Present or Absent below, or click "Mark All Active Present" above to record attendance.`
          )
        )
      ) : null,

      // CONVENIENT SHEET-WISE TABS
      h('div', { style: 'margin-bottom:1.25rem;' },
        h('div', { style: 'display:flex;justify-content:space-between;align-items:center;margin-bottom:0.45rem;' },
          h('div', { style: 'font-size:0.8rem;font-weight:700;text-transform:uppercase;color:var(--mut);' }, 'Select Master Sheet:'),
          f.sheet ? h('button', { class: 'btn sm', style: 'padding:0.15rem 0.5rem;font-size:0.75rem;', onclick: () => navTo({ sheet: '' }) }, 'Clear Sheet Filter ✕') : null
        ),
        h('div', { style: 'display:flex;gap:0.45rem;overflow-x:auto;padding-bottom:0.5rem;-webkit-overflow-scrolling:touch;' },
          h('button', {
            class: `btn sm ${!f.sheet ? 'pri' : ''}`,
            style: 'white-space:nowrap;flex-shrink:0;',
            onclick: () => navTo({ sheet: '' })
          }, `All Sheets (${items.length})`),
          ...sheets.map(sh => h('button', {
            class: `btn sm ${f.sheet === sh ? 'pri' : ''}`,
            style: 'white-space:nowrap;flex-shrink:0;',
            onclick: () => navTo({ sheet: sh })
          }, `${sh} (${sheetCounts[sh] || 0})`))
        )
      ),

      // Sheet Summary KPI Boxes (Present, Absent, Departed, Pending)
      h('div', { class: 'grid g4', style: 'margin-bottom:1.25rem;' },
        h('div', { style: 'background:var(--ok-bg);border:1px solid #bbf7d0;border-radius:var(--r-sm);padding:0.75rem 1rem;display:flex;justify-content:space-between;align-items:center;cursor:pointer;', onclick: () => navTo({ statusFilter: f.statusFilter === 'present' ? '' : 'present' }) },
          h('div', {},
            h('div', { style: 'font-size:0.75rem;font-weight:700;color:var(--ok);text-transform:uppercase;' }, `${f.sheet || 'Total'} Present`),
            h('div', { class: 'val', id: 'kpi-att-present', style: 'font-size:1.45rem;font-weight:700;color:var(--ok);' }, num(presentCount))
          ),
          badge('Present Today', 'ok')
        ),
        h('div', { style: 'background:var(--bad-bg);border:1px solid #fecaca;border-radius:var(--r-sm);padding:0.75rem 1rem;display:flex;justify-content:space-between;align-items:center;cursor:pointer;', onclick: () => navTo({ statusFilter: f.statusFilter === 'absent' ? '' : 'absent' }) },
          h('div', {},
            h('div', { style: 'font-size:0.75rem;font-weight:700;color:var(--bad);text-transform:uppercase;' }, `${f.sheet || 'Total'} Absent`),
            h('div', { class: 'val', id: 'kpi-att-absent', style: 'font-size:1.45rem;font-weight:700;color:var(--bad);' }, num(absentCount))
          ),
          badge('Absent Today', 'bad')
        ),
        h('div', { style: 'background:#fef3c7;border:1px solid #fde68a;border-radius:var(--r-sm);padding:0.75rem 1rem;display:flex;justify-content:space-between;align-items:center;cursor:pointer;', onclick: () => navTo({ statusFilter: f.statusFilter === 'departed' ? '' : 'departed' }) },
          h('div', {},
            h('div', { style: 'font-size:0.75rem;font-weight:700;color:#92400e;text-transform:uppercase;' }, `${f.sheet || 'Total'} Departed`),
            h('div', { class: 'val', id: 'kpi-att-departed', style: 'font-size:1.45rem;font-weight:700;color:#92400e;' }, num(departedCount))
          ),
          badge('Departed', 'warn')
        ),
        h('div', { style: 'background:var(--grey-bg);border:1px solid var(--line);border-radius:var(--r-sm);padding:0.75rem 1rem;display:flex;justify-content:space-between;align-items:center;cursor:pointer;', onclick: () => navTo({ statusFilter: f.statusFilter === 'pending' ? '' : 'pending' }) },
          h('div', {},
            h('div', { style: 'font-size:0.75rem;font-weight:700;color:var(--mut);text-transform:uppercase;' }, `${f.sheet || 'Total'} Pending`),
            h('div', { class: 'val', id: 'kpi-att-pending', style: 'font-size:1.45rem;font-weight:700;color:var(--ink);' }, num(notRecordedCount))
          ),
          badge('Pending Marking', 'grey')
        )
      ),

      // Filter & Search Controls
      h('div', { class: 'filter-bar' },
        h('div', { class: 'filters-grid', style: 'grid-template-columns:1fr 200px 180px;' },
          h('div', {},
            h('label', {}, 'Quick Staff Search'),
            h('input', {
              type: 'search',
              placeholder: `Search staff in ${f.sheet || 'all sheets'}…`,
              value: f.q,
              oninput: (e) => navTo({ q: e.target.value })
            })
          ),
          h('div', {},
            h('label', {}, 'Filter Location'),
            h('select', { onchange: (e) => navTo({ location: e.target.value }) },
              h('option', { value: '' }, 'All Locations'),
              ...locations.map(loc => h('option', { value: loc, selected: loc === f.location }, loc))
            )
          ),
          h('div', {},
            h('label', {}, 'Status View'),
            h('select', { onchange: (e) => navTo({ statusFilter: e.target.value }) },
              h('option', { value: '', selected: !f.statusFilter }, 'All Staff'),
              h('option', { value: 'present', selected: f.statusFilter === 'present' }, `Present (${presentCount})`),
              h('option', { value: 'absent', selected: f.statusFilter === 'absent' }, `Absent (${absentCount})`),
              h('option', { value: 'departed', selected: f.statusFilter === 'departed' }, `Departed (${departedCount})`),
              h('option', { value: 'pending', selected: f.statusFilter === 'pending' }, `Pending (${notRecordedCount})`)
            )
          )
        )
      ),

      // Sheet-Wise Roster Display
      Object.keys(groupedBySheet).length > 0 ? h('div', { style: 'display:flex;flex-direction:column;gap:1.5rem;' },
        ...Object.entries(groupedBySheet).map(([sheetName, sheetStaff]) => {
          const shPresent = sheetStaff.filter(r => r.status !== 'Departed' && r.att === 'Present').length;
          const shAbsent = sheetStaff.filter(r => r.status !== 'Departed' && r.att === 'Absent').length;
          const shDeparted = sheetStaff.filter(r => r.status === 'Departed').length;
          const shPending = sheetStaff.filter(r => r.status !== 'Departed' && (!r.att || r.att === 'Not Recorded')).length;

          return h('div', { class: 'card', style: 'padding:1rem 1.15rem;' },
            // Sheet Sub-Header with 1-click sheet bulk actions
            h('div', { class: 'card-header', style: 'margin-bottom:0.75rem;' },
              h('div', { style: 'display:flex;align-items:center;gap:0.65rem;flex-wrap:wrap;' },
                h('h3', { class: 'card-title' }, `Sheet: ${sheetName}`),
                badge(`${sheetStaff.length} staff`, 'teal'),
                badge(`${shPresent} Present`, 'ok'),
                shAbsent > 0 ? badge(`${shAbsent} Absent`, 'bad') : null,
                shDeparted > 0 ? badge(`${shDeparted} Departed`, 'warn') : null,
                shPending > 0 ? badge(`${shPending} Pending`, 'grey') : null
              ),
              canEdit ? h('div', { style: 'display:flex;gap:0.4rem;' },
                h('button', {
                  class: 'btn sm teal',
                  onclick: () => markSheetAllPresent(sheetName)
                }, `✓ Mark All Active Present`),
                h('button', {
                  class: 'btn sm',
                  title: 'Clear attendance for this sheet',
                  onclick: () => clearSheetAttendance(sheetName)
                }, 'Reset Sheet')
              ) : null
            ),

            // Sheet Attendance Table
            h('div', { class: 'tw resp' },
              h('table', {},
                h('thead', {},
                  h('tr', {},
                    h('th', {}, 'Staff Name'),
                    h('th', {}, 'Designation'),
                    h('th', {}, 'Location'),
                    h('th', {}, 'Recorded Status'),
                    h('th', { style: 'text-align:right;' }, 'Attendance & Status Action')
                  )
                ),
                h('tbody', {},
                  ...sheetStaff.map(r => {
                    const isDep = r.status === 'Departed';
                    const curAtt = r.att || 'Not Recorded';
                    const safeId = r.ref.replace(/[^a-zA-Z0-9_-]/g, '_');

                    return h('tr', { id: `att-row-${safeId}` },
                      h('td', { style: 'font-weight:600;' },
                        h('a', { href: `#/employee/${encodeURIComponent(r.ref)}` }, r.name),
                        r.id ? h('div', { style: 'font-size:0.75rem;color:var(--mut);font-weight:400;' }, r.id) : null
                      ),
                      h('td', {}, r.designation || '—'),
                      h('td', {}, r.location || '—'),
                      h('td', { class: 'status-cell' },
                        isDep ? badge('Departed', 'warn') :
                        curAtt === 'Present' ? badge('Present', 'ok') :
                        curAtt === 'Absent' ? badge('Absent', 'bad') :
                        badge('Not Recorded', 'grey')
                      ),
                      h('td', { style: 'text-align:right;' },
                        h('div', { class: 'att' },
                          h('button', {
                            class: `btn-att-present ${!isDep && curAtt === 'Present' ? 'on Present' : ''}`,
                            disabled: !canEdit,
                            title: isDep ? 'Click to reactivate staff and mark Present' : 'Mark staff Present today',
                            onclick: (e) => markStaffPresent(r, e.currentTarget)
                          }, 'Present'),
                          h('button', {
                            class: `btn-att-absent ${!isDep && curAtt === 'Absent' ? 'on Absent' : ''}`,
                            disabled: !canEdit,
                            title: isDep ? 'Click to reactivate staff and mark Absent' : 'Mark staff Absent today',
                            onclick: (e) => markStaffAbsent(r, e.currentTarget)
                          }, 'Absent'),
                          h('button', {
                            class: `btn-att-departed ${isDep ? 'on Departed' : ''}`,
                            disabled: !canEdit,
                            title: isDep ? 'Employee is Departed' : 'Mark employee as Departed',
                            onclick: (e) => markStaffDeparted(r, e.currentTarget)
                          }, 'Departed'),
                          h('button', {
                            class: 'btn sm btn-att-reset',
                            style: `display:${(!isDep && curAtt !== 'Not Recorded' && canEdit) ? 'inline-flex' : 'none'};`,
                            title: 'Reset to Not Recorded',
                            onclick: (e) => updateStatus(r, 'Not Recorded', e.currentTarget)
                          }, '✕')
                        )
                      )
                    );
                  })
                )
              ),

              // Mobile Cards Alternative
              h('div', { class: 'ecards' },
                ...sheetStaff.map(r => {
                  const isDep = r.status === 'Departed';
                  const curAtt = r.att || 'Not Recorded';
                  const safeId = r.ref.replace(/[^a-zA-Z0-9_-]/g, '_');

                  return h('div', { class: 'ecard', id: `att-card-${safeId}` },
                    h('div', { class: 'ecard-top' },
                      h('a', { class: 'ecard-name', href: `#/employee/${encodeURIComponent(r.ref)}` }, r.name),
                      h('div', { class: 'ecard-status-badge' },
                        isDep ? badge('Departed', 'warn') :
                        curAtt === 'Present' ? badge('Present', 'ok') :
                        curAtt === 'Absent' ? badge('Absent', 'bad') :
                        badge('Not Recorded', 'grey')
                      )
                    ),
                    h('div', { class: 'ecard-meta' }, `${r.designation || 'Staff'} · ${r.location || 'Location missing'}`),
                    h('div', { style: 'display:flex;gap:0.4rem;margin-top:0.75rem;flex-wrap:wrap;' },
                      h('button', {
                        class: `btn sm mbtn-present ${!isDep && curAtt === 'Present' ? 'teal' : ''}`,
                        style: 'flex:1;justify-content:center;min-width:70px;',
                        disabled: !canEdit,
                        onclick: (e) => markStaffPresent(r, e.currentTarget)
                      }, 'Present'),
                      h('button', {
                        class: `btn sm mbtn-absent ${!isDep && curAtt === 'Absent' ? 'dng' : ''}`,
                        style: 'flex:1;justify-content:center;min-width:70px;',
                        disabled: !canEdit,
                        onclick: (e) => markStaffAbsent(r, e.currentTarget)
                      }, 'Absent'),
                      h('button', {
                        class: `btn sm mbtn-departed ${isDep ? 'warn' : ''}`,
                        style: `flex:1;justify-content:center;min-width:75px;${isDep ? 'background:#fef3c7;border-color:#f59e0b;color:#92400e;font-weight:700;' : ''}`,
                        disabled: !canEdit,
                        onclick: (e) => markStaffDeparted(r, e.currentTarget)
                      }, 'Departed'),
                      h('button', {
                        class: 'btn sm mbtn-reset',
                        style: `display:${(!isDep && curAtt !== 'Not Recorded' && canEdit) ? 'inline-flex' : 'none'};`,
                        onclick: (e) => updateStatus(r, 'Not Recorded', e.currentTarget)
                      }, '✕')
                    )
                  );
                })
              )
            )
          );
        })
      ) : empty('No staff matching filters', 'No employees found in the selected sheet or filter.', '👥')
    );

    setKids(main, content);
  } catch (err) {
    setKids(main, empty('Error loading attendance', err.message, '⚠️'));
  }
}

export async function renderPayroll(main, query) {
  setKids(main, h('div', { style: 'padding:2rem;text-align:center;color:var(--mut)' }, 'Loading operational work records…'));

  try {
    const [payData, bootstrap] = await Promise.all([
      api.get(`/api/payroll?status=all`),
      api.get('/api/bootstrap')
    ]);

    const content = h('div', {},
      h('div', { class: 'top' },
        h('div', { class: 'top-title' },
          h('h1', {}, 'Work Records & Operational Days'),
          h('div', { class: 'sub' }, 'Operational attendance day counts. Financial calculations are locked under company policy.')
        ),
        h('div', { class: 'top-actions' },
          badge('Rates Unauthorized', 'warn'),
          badge('Payment Calculations Locked', 'bad')
        )
      ),

      // Policy Safeguard Banner
      policySafeguard('Financial Policy Safeguard: No employee compensation rates are approved. No payment amount is calculated, owed, or authorized. Existing spreadsheet figures are displayed below for historical provenance only.'),

      // Operational Summary KPIs
      h('div', { class: 'grid g3', style: 'margin-bottom:1.25rem;' },
        h('div', { class: 'stat-card' },
          h('div', { class: 'label' }, 'Total Recorded Staff'),
          h('div', { class: 'val' }, num((payData.rows || payData.employees || []).length || (payData.summary && payData.summary.total) || 0)),
          h('div', { class: 'subtext' }, 'Across all master sheets')
        ),
        h('div', { class: 'stat-card primary' },
          h('div', { class: 'label' }, 'Total Legacy Present Days'),
          h('div', { class: 'val' }, num(payData.summary ? (payData.summary.legacy_present_days || (payData.summary.pay && payData.summary.pay.total_legacy_days) || 0) : 0)),
          h('div', { class: 'subtext' }, 'Recorded September + October days')
        ),
        h('div', { class: 'stat-card danger' },
          h('div', { class: 'label' }, 'Authorized Payable Obligations'),
          h('div', { class: 'val' }, '₹0.00'),
          h('div', { class: 'subtext' }, 'All calculations withheld by policy')
        )
      ),

      // Consolidated Staff Work-Day Table
      h('div', { class: 'card' },
        h('div', { class: 'card-header' },
          h('h3', { class: 'card-title' }, 'Consolidated Staff Work Days Roster')
        ),
        h('div', { class: 'tw' },
          h('table', {},
            h('thead', {},
              h('tr', {},
                h('th', {}, 'Employee Name'),
                h('th', {}, 'Source Sheet'),
                h('th', { class: 'n' }, 'Sept Legacy Days'),
                h('th', { class: 'n' }, 'Oct Legacy Days'),
                h('th', { class: 'n' }, 'Total Present Days'),
                h('th', { class: 'n' }, 'Raw Source Rate'),
                h('th', {}, 'Authorization Status')
              )
            ),
            h('tbody', {},
              ...(payData.rows || payData.employees || []).map(e => h('tr', {},
                h('td', { style: 'font-weight:600;' },
                  h('a', { href: `#/employee/${encodeURIComponent(e.ref)}` }, e.name)
                ),
                h('td', {},
                  h('a', { href: `#/employees?sheet=${encodeURIComponent(e.group || e.sheet || '')}`, title: `View ${e.group || e.sheet} staff` }, badge(e.group || e.sheet || 'Sheet', 'grey'))
                ),
                h('td', { class: 'n' }, num(e.sept || (e.legacy && e.legacy.sept) || 0)),
                h('td', { class: 'n' }, num(e.octo || (e.legacy && e.legacy.octo) || 0)),
                h('td', { class: 'n', style: 'font-weight:600;' }, num(e.legacy_days || (e.legacy && e.legacy.days) || 0)),
                h('td', { class: 'n' }, e.rate ? inr(e.rate) : '—'),
                h('td', {}, badge('Unapproved', 'indigo'))
              ))
            )
          )
        )
      )
    );

    setKids(main, content);
  } catch (err) {
    setKids(main, empty('Error loading work records', err.message, '⚠️'));
  }
}

export async function renderReports(main, query) {
  const f = {
    report: query.report || 'all_employees',
    sheet: query.sheet || '',
    date: query.date || today()
  };

  setKids(main, h('div', { style: 'padding:2rem;text-align:center;color:var(--mut)' }, 'Loading reports workspace…'));

  try {
    const [reportData, bootstrap] = await Promise.all([
      api.get(`/api/reports/${f.report}?${qs({ group: f.sheet, date: f.date })}`),
      api.get('/api/bootstrap')
    ]);

    const sheets = bootstrap.groups || [];

    const navTo = (updates) => {
      const merged = { ...f, ...updates };
      location.hash = `#/reports?${qs(merged)}`;
    };

    const downloadCsv = () => {
      window.open(`/api/reports/${f.report}?${qs({ group: f.sheet, date: f.date, format: 'csv' })}`, '_blank');
    };

    const downloadXlsx = () => {
      window.open(`/api/reports/${f.report}?${qs({ group: f.sheet, date: f.date, format: 'xlsx' })}`, '_blank');
    };

    const content = h('div', {},
      h('div', { class: 'top' },
        h('div', { class: 'top-title' },
          h('h1', {}, 'Operational Reports & Data Exports'),
          h('div', { class: 'sub' }, 'Audit-ready reports with masked personal identifiers and zero invented financial liabilities.')
        ),
        h('div', { class: 'top-actions' },
          h('button', { class: 'btn sm', onclick: downloadCsv }, '📥 Download CSV'),
          h('button', { class: 'btn sm pri', onclick: downloadXlsx }, '📊 Download Excel (.xlsx)')
        )
      ),

      policySafeguard('All report exports omit unapproved compensation and payable totals per financial integrity policy. Sensitive columns are masked for privacy compliance.'),

      h('div', { class: 'filter-bar' },
        h('div', { class: 'filters-grid' },
          h('div', {},
            h('label', {}, 'Select Report Type'),
            h('select', { onchange: (e) => navTo({ report: e.target.value }) },
              h('option', { value: 'all_employees', selected: f.report === 'all_employees' }, 'Master Staff Directory (All Employees)'),
              h('option', { value: 'daily_attendance', selected: f.report === 'daily_attendance' }, 'Daily Attendance Summary'),
              h('option', { value: 'departed', selected: f.report === 'departed' }, 'Departure & Status History'),
              h('option', { value: 'data_quality', selected: f.report === 'data_quality' }, 'Data Completeness Audit')
            )
          ),
          h('div', {},
            h('label', {}, 'Filter Source Sheet'),
            h('select', { onchange: (e) => navTo({ sheet: e.target.value }) },
              h('option', { value: '' }, 'All Sheets (Consolidated)'),
              ...sheets.map(sh => h('option', { value: sh, selected: sh === f.sheet }, sh))
            )
          ),
          h('div', {},
            h('label', {}, 'Reporting Date'),
            h('input', {
              type: 'date',
              value: f.date,
              onchange: (e) => navTo({ date: e.target.value })
            })
          )
        )
      ),

      h('div', { class: 'card' },
        h('div', { class: 'card-header' },
          h('h3', { class: 'card-title' }, `Report Preview: ${reportData.title || f.report}`),
          h('span', { style: 'font-size:0.82rem;color:var(--mut);' }, `${(reportData.rows || []).length} rows generated`)
        ),
        h('div', { class: 'tw' },
          h('table', {},
            h('thead', {},
              h('tr', {},
                ...(reportData.columns || ['Group', 'Name', 'Location', 'Status']).map(col => h('th', {}, Array.isArray(col) ? col[1] : col))
              )
            ),
            h('tbody', {},
              ...(reportData.rows || []).map(row => h('tr', {},
                ...(Array.isArray(row) ? row : Object.values(row)).map(cell => h('td', {}, String(cell == null ? '—' : cell)))
              ))
            )
          )
        )
      )
    );

    setKids(main, content);
  } catch (err) {
    setKids(main, empty('Error generating report', err.message, '⚠️'));
  }
}

export async function renderDeparted(main, query) {
  setKids(main, h('div', { style: 'padding:2rem;text-align:center;color:var(--mut)' }, 'Loading departed staff records…'));

  try {
    const [data, bootstrap] = await Promise.all([
      api.get('/api/departed'),
      api.get('/api/bootstrap')
    ]);

    const canEdit = bootstrap.role === 'admin' || bootstrap.role === 'editor';
    const items = data.items || [];
    const sheets = bootstrap.groups || [];

    const reactivateStaff = async (ref, name) => {
      const ok = await confirmBox(
        'Reactivate Staff Member',
        `Reinstate ${name} back to Active employee status?`
      );
      if (!ok) return;

      try {
        await api.post(`/api/status/${encodeURIComponent(ref)}`, { status: 'Active' });
        toast(`${name} reinstated as Active`, 'ok');
        renderDeparted(main, query);
      } catch (err) {
        toast(err.message || 'Reactivation failed', 'bad');
      }
    };

    const openRecordDepartureModal = () => {
      let selectedRef = '';
      let depDate = today();
      let depReason = 'Resigned';
      let customNotes = '';

      const empSelect = h('select', { onchange: (e) => selectedRef = e.target.value },
        h('option', { value: '' }, '— Select Employee —')
      );

      // Load active employees into selector
      api.get('/api/employees?status=Active&page_size=300').then(res => {
        const staff = res.items || [];
        setKids(empSelect,
          h('option', { value: '' }, '— Select Employee —'),
          ...staff.map(s => h('option', { value: s.ref }, `${s.name} (${s.group || 'Sheet'})`))
        );
      });

      const body = h('div', { class: 'filters-grid', style: 'grid-template-columns:1fr;gap:0.75rem;' },
        h('div', {},
          h('label', {}, 'Select Employee *'),
          empSelect
        ),
        h('div', {},
          h('label', {}, 'Confirmed Departure Date *'),
          h('input', {
            type: 'date',
            value: depDate,
            max: today(),
            onchange: (e) => depDate = e.target.value
          })
        ),
        h('div', {},
          h('label', {}, 'Reason for Departure'),
          h('select', { onchange: (e) => depReason = e.target.value },
            h('option', { value: 'Resigned' }, 'Resigned (Career / Personal)'),
            h('option', { value: 'Contract Completed' }, 'Contract Completed'),
            h('option', { value: 'Seasonal Exit' }, 'Seasonal Exit (Post-Festival)'),
            h('option', { value: 'Relocated' }, 'Relocated to hometown'),
            h('option', { value: 'Health / Personal' }, 'Health / Family reasons'),
            h('option', { value: 'Other' }, 'Other (specified in notes)')
          )
        ),
        h('div', {},
          h('label', {}, 'Operational Notes (No Financial Debt Inferred)'),
          h('textarea', {
            rows: 2,
            placeholder: 'e.g. Handover completed, equipment returned…',
            oninput: (e) => customNotes = e.target.value
          })
        )
      );

      modal('Record Staff Departure', body, async () => {
        if (!selectedRef) {
          toast('Please select an employee', 'bad');
          return false;
        }
        if (!depDate) {
          toast('Departure date is required', 'bad');
          return false;
        }
        try {
          await api.post(`/api/status/${encodeURIComponent(selectedRef)}`, {
            status: 'Departed',
            dep_date: depDate,
            reason: `${depReason}${customNotes ? ': ' + customNotes : ''}`
          });
          toast('Staff departure recorded', 'ok');
          renderDeparted(main, query);
          return true;
        } catch (err) {
          toast(err.message || 'Failed to record departure', 'bad');
          return false;
        }
      }, 'Confirm Departure');
    };

    const recentDepartures = items.filter(r => r.recent).length;

    const content = h('div', {},
      h('div', { class: 'top' },
        h('div', { class: 'top-title' },
          h('h1', {}, 'Departed Staff & Historical Management'),
          h('div', { class: 'sub' }, 'Manage employee departures, track departure reasons, and preserve historical attendance integrity.')
        ),
        canEdit ? h('div', { class: 'top-actions' },
          h('button', {
            class: 'btn pri',
            onclick: openRecordDepartureModal
          }, '+ Record Staff Departure')
        ) : null
      ),

      // Smart Departure KPIs
      h('div', { class: 'grid g3', style: 'margin-bottom:1.25rem;' },
        h('div', { class: 'stat-card' },
          h('div', { class: 'label' }, 'All-Time Departures'),
          h('div', { class: 'val' }, num(items.length)),
          h('div', { class: 'subtext' }, 'Historical work records preserved')
        ),
        h('div', { class: 'stat-card warning' },
          h('div', { class: 'label' }, 'Recent Departures (30 Days)'),
          h('div', { class: 'val' }, num(recentDepartures)),
          h('div', { class: 'subtext' }, 'Recent turnover window')
        ),
        h('div', { class: 'stat-card success' },
          h('div', { class: 'label' }, 'Active Workforce'),
          h('div', { class: 'val' }, num(data.active_count != null ? data.active_count : (data.total_staff ? data.total_staff - items.length : ((bootstrap.total_employees || 0) - items.length)))),
          h('div', { class: 'subtext' }, 'Currently engaged staff')
        )
      ),

      // Departed Table
      items.length > 0 ? h('div', { class: 'card' },
        h('div', { class: 'card-header' },
          h('h3', { class: 'card-title' }, `Departed Employees Roster (${items.length})`),
          h('span', { style: 'font-size:0.82rem;color:var(--mut);' }, 'Departure records are tamper-evident')
        ),
        h('div', { class: 'tw' },
          h('table', {},
            h('thead', {},
              h('tr', {},
                h('th', {}, 'Employee Name'),
                h('th', {}, 'Original Sheet'),
                h('th', {}, 'Location'),
                h('th', {}, 'Departure Date'),
                h('th', {}, 'Recorded Reason'),
                h('th', {}, 'Status'),
                canEdit ? h('th', { style: 'text-align:right;' }, 'Action') : null
              )
            ),
            h('tbody', {},
              ...items.map(r => h('tr', {},
                h('td', { style: 'font-weight:600;' },
                  h('a', { href: `#/employee/${encodeURIComponent(r.ref)}` }, r.name),
                  r.recent ? h('span', { style: 'margin-left:0.4rem;' }, badge('Recent', 'warn')) : null
                ),
                h('td', {},
                  h('a', { href: `#/employees?sheet=${encodeURIComponent(r.group || '')}`, title: `View ${r.group} staff` }, badge(r.group || 'Sheet', 'grey'))
                ),
                h('td', {}, r.location || '—'),
                h('td', {}, fdate(r.dep_date)),
                h('td', {}, r.dep_reason || '—'),
                h('td', {}, badge('Departed', 'bad')),
                canEdit ? h('td', { style: 'text-align:right;' },
                  h('button', {
                    class: 'btn sm',
                    title: 'Reinstate employee back to Active',
                    onclick: () => reactivateStaff(r.ref, r.name)
                  }, 'Reactivate Staff')
                ) : null
              ))
            )
          )
        )
      ) : empty('No departed staff records', 'Click "+ Record Staff Departure" above to record an employee departure with a confirmed date.', '📁')
    );

    setKids(main, content);
  } catch (err) {
    setKids(main, empty('Error loading departed staff', err.message, '⚠️'));
  }
}
