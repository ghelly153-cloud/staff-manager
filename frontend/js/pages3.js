// Pages: Admin Workspace (Issues, Status Review, Pay Rules, Options, Workbook Setup, Audit Log) and Sync Health.
import { api } from './api.js';
import { h, setKids, num, fdate, badge, policySafeguard, empty, toast, confirmBox, modal, qs } from './ui.js';

export async function renderAdmin(main, query) {
  const tab = query.tab || 'issues';

  setKids(main, h('div', { style: 'padding:2rem;text-align:center;color:var(--mut)' }, 'Loading administration panel…'));

  try {
    const bootstrap = await api.get('/api/bootstrap');
    const isAdmin = bootstrap.role === 'admin';

    const content = h('div', {},
      h('div', { class: 'top' },
        h('div', { class: 'top-title' },
          h('h1', {}, 'System Administration & Data Governance'),
          h('div', { class: 'sub' }, 'Manage data quality, employee status verification, workbook schema setup, and audit logs.')
        ),
        h('div', { class: 'top-actions' },
          badge(isAdmin ? 'Administrator Access' : 'Editor Access', isAdmin ? 'ok' : 'grey')
        )
      ),

      // Admin Sub-Navigation
      h('div', { style: 'display:flex;gap:0.4rem;border-bottom:1px solid var(--line);margin-bottom:1.5rem;overflow-x:auto;padding-bottom:0.1rem;' },
        ...[
          ['issues', 'Quality Issues'],
          ['review', 'Status Review'],
          ['payrules', 'Pay Rules & Policy'],
          ['options', 'System Options'],
          ['setup', 'Workbook Setup'],
          ['audit', 'Audit Log']
        ].map(([id, label]) => h('a', {
          href: `#/admin?tab=${id}`,
          class: `btn sm ${tab === id ? 'pri' : ''}`,
          style: tab === id ? '' : 'background:transparent;border-color:transparent;'
        }, label))
      ),

      // Tab Content Outlet
      h('div', { id: 'admin-tab-content' })
    );

    setKids(main, content);
    const tabOutlet = document.getElementById('admin-tab-content');

    if (tab === 'issues') renderIssuesTab(tabOutlet, query);
    else if (tab === 'review') renderReviewTab(tabOutlet, isAdmin);
    else if (tab === 'payrules') renderPayRulesTab(tabOutlet);
    else if (tab === 'options') renderOptionsTab(tabOutlet, isAdmin);
    else if (tab === 'setup') renderSetupTab(tabOutlet, isAdmin);
    else if (tab === 'audit') renderAuditTab(tabOutlet);
  } catch (err) {
    setKids(main, empty('Error loading admin workspace', err.message, '⚠️'));
  }
}

async function renderIssuesTab(container, query) {
  setKids(container, h('div', { style: 'padding:1.5rem;text-align:center;color:var(--mut)' }, 'Checking workbook quality issues…'));
  try {
    const data = await api.get('/api/quality');
    const allItems = data.items || [];
    const activeFilter = query.sev || '';

    const reviewItems = allItems.filter(i => i.severity === 'review' || i.severity === 'error');
    const infoItems = allItems.filter(i => i.severity === 'info');

    const items = activeFilter === 'review' ? reviewItems :
                  activeFilter === 'info' ? infoItems : allItems;

    const resolveSingle = async (it) => {
      try {
        await api.post('/api/quality/resolve', {
          fingerprint: it.fingerprint,
          note: 'Acknowledged'
        });
        toast('Observation acknowledged', 'ok');
        renderIssuesTab(container, query);
      } catch (err) {
        toast(err.message || 'Action failed', 'bad');
      }
    };

    const resolveAll = async () => {
      const ok = await confirmBox(
        'Acknowledge All Observations',
        `Acknowledge and mark all ${allItems.length} workbook observations as reviewed?`
      );
      if (!ok) return;

      try {
        await api.post('/api/quality/resolve-all', {
          note: 'Bulk acknowledged by administrator'
        });
        toast(`All ${allItems.length} observations acknowledged!`, 'ok');
        renderIssuesTab(container, query);
      } catch (err) {
        toast(err.message || 'Failed to acknowledge issues', 'bad');
      }
    };

    const content = h('div', {},
      h('div', { class: 'card-header', style: 'flex-wrap:wrap;gap:0.75rem;' },
        h('div', {},
          h('h3', { class: 'card-title' }, `Data Quality Audit (${items.length} ${activeFilter ? activeFilter : 'Total'} Observations)`),
          h('span', { style: 'font-size:0.82rem;color:var(--mut);' }, 'Continuous validation of workbook cells, identity fields, and structure')
        ),
        h('div', { style: 'display:flex;gap:0.5rem;align-items:center;' },
          allItems.length > 0 ? h('button', {
            class: 'btn sm teal',
            onclick: resolveAll
          }, `✓ Acknowledge All (${allItems.length})`) : null
        )
      ),

      // Severity Filter Tabs
      h('div', { style: 'display:flex;gap:0.4rem;margin-bottom:1rem;' },
        h('a', {
          href: '#/admin?tab=issues',
          class: `btn sm ${!activeFilter ? 'pri' : ''}`,
          style: !activeFilter ? '' : 'background:transparent;'
        }, `All Observations (${allItems.length})`),
        h('a', {
          href: '#/admin?tab=issues&sev=review',
          class: `btn sm ${activeFilter === 'review' ? 'pri' : ''}`,
          style: activeFilter === 'review' ? '' : 'background:transparent;'
        }, `Needs Review (${reviewItems.length})`),
        h('a', {
          href: '#/admin?tab=issues&sev=info',
          class: `btn sm ${activeFilter === 'info' ? 'pri' : ''}`,
          style: activeFilter === 'info' ? '' : 'background:transparent;'
        }, `Informational (${infoItems.length})`)
      ),

      items.length > 0 ? h('div', { class: 'tw' },
        h('table', {},
          h('thead', {},
            h('tr', {},
              h('th', {}, 'Severity'),
              h('th', {}, 'Workbook Sheet'),
              h('th', {}, 'Row'),
              h('th', {}, 'Observation Description'),
              h('th', {}, 'Recommended Safe Action'),
              h('th', { style: 'text-align:right;' }, 'Action')
            )
          ),
          h('tbody', {},
            ...items.map(it => h('tr', {},
              h('td', {},
                it.severity === 'error' ? badge('Error', 'bad') :
                it.severity === 'review' ? badge('Review', 'warn') :
                badge('Observation', 'grey')
              ),
              h('td', { style: 'font-weight:600;' },
                it.sheet && it.sheet !== 'Workbook' ? h('a', {
                  href: `#/employees?sheet=${encodeURIComponent(it.sheet)}`,
                  title: `Inspect ${it.sheet} sheet roster`
                }, it.sheet) : (it.sheet || 'Workbook')
              ),
              h('td', {}, it.row ? String(it.row) : '—'),
              h('td', { style: 'font-weight:500;' }, it.message),
              h('td', { style: 'font-size:0.82rem;color:var(--mut);' }, it.detail || 'Review cell value in spreadsheet'),
              h('td', { style: 'text-align:right;' },
                h('button', {
                  class: 'btn sm',
                  onclick: () => resolveSingle(it)
                }, 'Acknowledge')
              )
            ))
          )
        )
      ) : empty('Zero blocking issues found', 'All workbook cells and employee records adhere to established validation rules.', '✓')
    );
    setKids(container, content);
  } catch (err) {
    setKids(container, empty('Error loading issues', err.message, '⚠️'));
  }
}

async function renderReviewTab(container, isAdmin) {
  setKids(container, h('div', { style: 'padding:1.5rem;text-align:center;color:var(--mut)' }, 'Loading unverified staff records…'));
  try {
    const data = await api.get('/api/employees?status=Not Verified&page_size=200');
    const items = data.items || [];
    const canEdit = isAdmin || (window.__currentUser && (window.__currentUser.role === 'admin' || window.__currentUser.role === 'editor'));

    const setStatus = async (ref, status) => {
      try {
        await api.post(`/api/status/${encodeURIComponent(ref)}`, { status });
        toast(`Employee status updated to ${status}`, 'ok');
        renderReviewTab(container, isAdmin);
      } catch (err) {
        toast(err.message || 'Status update failed', 'bad');
      }
    };

    const confirmAllActive = async () => {
      const ok = await confirmBox(
        'Confirm All Staff as Active',
        `Confirm all ${items.length} pending staff members as Active employees in the master workbook?`
      );
      if (!ok) return;

      try {
        await api.post('/api/status', {
          confirmed: true,
          items: items.map(r => ({ ref: r.ref, status: 'Active' }))
        });
        toast(`All ${items.length} staff confirmed as Active!`, 'ok');
        renderReviewTab(container, isAdmin);
      } catch (err) {
        toast(err.message || 'Bulk confirmation failed', 'bad');
      }
    };

    const content = h('div', {},
      h('div', { class: 'card-header' },
        h('h3', { class: 'card-title' }, `Status Verification Workflow (${items.length} Pending)`),
        items.length > 0 && canEdit ? h('button', {
          class: 'btn sm teal',
          onclick: confirmAllActive
        }, `✓ Confirm All ${items.length} as Active`) : h('span', { style: 'font-size:0.82rem;color:var(--ok);font-weight:600;' }, 'All Roster Records Verified Active')
      ),
      items.length > 0 ? h('div', { class: 'tw' },
        h('table', {},
          h('thead', {},
            h('tr', {},
              h('th', {}, 'Employee Name'),
              h('th', {}, 'Sheet'),
              h('th', {}, 'Location'),
              h('th', {}, 'Current Status'),
              h('th', { style: 'text-align:right;' }, 'Verification Action')
            )
          ),
          h('tbody', {},
            ...items.map(r => h('tr', {},
              h('td', { style: 'font-weight:600;' },
                h('a', { href: `#/employee/${encodeURIComponent(r.ref)}` }, r.name)
              ),
              h('td', {},
                h('a', { href: `#/employees?sheet=${encodeURIComponent(r.group || '')}` }, badge(r.group || 'Sheet', 'grey'))
              ),
              h('td', {}, r.location || '—'),
              h('td', {}, badge('Not Verified', 'warn')),
              h('td', { style: 'text-align:right;' },
                h('div', { style: 'display:inline-flex;gap:0.4rem;' },
                  h('button', {
                    class: 'btn sm teal',
                    disabled: !canEdit,
                    onclick: () => setStatus(r.ref, 'Active')
                  }, 'Confirm Active'),
                  h('button', {
                    class: 'btn sm dng',
                    disabled: !canEdit,
                    onclick: () => setStatus(r.ref, 'Departed')
                  }, 'Mark Departed')
                )
              )
            ))
          )
        )
      ) : empty('All staff records verified in master workbook', 'Every employee in the Excel sheets is confirmed as an Active staff member.', '✓')
    );
    setKids(container, content);
  } catch (err) {
    setKids(container, empty('Error loading review', err.message, '⚠️'));
  }
}

function renderPayRulesTab(container) {
  const content = h('div', { class: 'card' },
    h('div', { class: 'card-header' },
      h('h3', { class: 'card-title' }, 'Compensation Policy & Rate Authorization Lockout')
    ),
    policySafeguard('Financial Policy Override Enforced: Under company policy, no employee has an authorized compensation rate. All legacy workbook formulas multiplying days by rates are deactivated. No payment amounts will be authorized, owed, or calculated.'),
    h('div', { style: 'line-height:1.6;font-size:0.9rem;color:var(--ink);' },
      h('p', { style: 'margin-bottom:1rem;' },
        'To protect financial integrity, this system does not infer or assume any wage, salary, per-day allowance, or payment obligation. The legacy numbers in the master Excel workbook (such as ₹100 formulas or ₹17,900 totals) are treated strictly as unverified historical cells.'
      ),
      h('p', { style: 'margin-bottom:1rem;' },
        'If an approved compensation policy is introduced in the future by executive management, it must be formally introduced through an authenticated administrative approval workflow with audited rate definitions.'
      )
    )
  );
  setKids(container, content);
}

async function renderOptionsTab(container, isAdmin) {
  setKids(container, h('div', { style: 'padding:1.5rem;text-align:center;color:var(--mut)' }, 'Loading system options…'));
  try {
    const cfg = await api.get('/api/options');
    const content = h('div', { class: 'card' },
      h('div', { class: 'card-header' },
        h('h3', { class: 'card-title' }, 'System Configuration Options')
      ),
      h('div', { style: 'display:flex;flex-direction:column;gap:1rem;' },
        h('div', {},
          h('label', {}, 'Configured Attendance Statuses:'),
          h('div', { style: 'display:flex;gap:0.5rem;flex-wrap:wrap;margin-top:0.3rem;' },
            ...(cfg.attendance_statuses || ['Present', 'Absent']).map(st => badge(st, 'teal'))
          )
        ),
        h('div', {},
          h('label', {}, 'Permanent ID Auto-Assignment:'),
          h('div', { style: 'font-weight:600;color:var(--ink);' }, cfg.auto_assign_ids ? 'Enabled (Generates EMP-xxxxxxxx)' : 'Disabled')
        ),
        h('div', {},
          h('label', {}, 'Application Timezone:'),
          h('div', { style: 'font-weight:600;color:var(--ink);' }, cfg.timezone || 'Asia/Kolkata')
        )
      )
    );
    setKids(container, content);
  } catch (err) {
    setKids(container, empty('Error loading options', err.message, '⚠️'));
  }
}

async function renderSetupTab(container, isAdmin) {
  setKids(container, h('div', { style: 'padding:1.5rem;text-align:center;color:var(--mut)' }, 'Inspecting workbook schema…'));
  try {
    const plan = await api.get('/api/setup/plan');
    const needsSetup = !plan.already_done;

    const runSetup = async () => {
      const ok = await confirmBox(
        'Execute Workbook Setup',
        'This will create a verified backup, assign permanent EMP-xxxxxxxx identifiers to unassigned staff, and create helper columns. Proceed?'
      );
      if (!ok) return;

      try {
        await api.post('/api/setup/run', { confirmed: true });
        toast('Workbook setup executed and verified successfully', 'ok');
        renderSetupTab(container, isAdmin);
      } catch (err) {
        toast(err.message || 'Setup execution failed', 'bad');
      }
    };

    const content = h('div', { class: 'card' },
      h('div', { class: 'card-header' },
        h('h3', { class: 'card-title' }, 'Master Workbook Setup & Migration'),
        badge(needsSetup ? 'Setup Needed' : 'Schema Verified', needsSetup ? 'warn' : 'ok')
      ),
      h('p', { style: 'font-size:0.88rem;color:var(--ink);margin-bottom:1.25rem;line-height:1.5;' },
        needsSetup
          ? 'The workbook requires permanent employee identifiers and helper columns to enable safe two-way writes. Running setup automatically creates a verified backup copy before applying changes.'
          : 'All sheets and helper columns are configured. Permanent employee identifiers are assigned and verified.'
      ),
      h('div', { style: 'background:var(--grey-bg);border-radius:var(--r-sm);padding:1rem;margin-bottom:1.5rem;font-size:0.85rem;' },
        h('div', { style: 'font-weight:700;margin-bottom:0.4rem;' }, 'Migration Plan Summary:'),
        h('div', {}, `Permanent IDs to assign: ${plan.ids_to_assign || 0}`),
        h('div', {}, `Helper support sheets: ${(plan.support_sheets_to_create || []).join(', ') || 'Already present'}`)
      ),
      needsSetup && isAdmin ? h('button', {
        class: 'btn pri',
        onclick: runSetup
      }, 'Run Safe Workbook Setup') : null
    );
    setKids(container, content);
  } catch (err) {
    setKids(container, empty('Error loading setup plan', err.message, '⚠️'));
  }
}

async function renderAuditTab(container) {
  setKids(container, h('div', { style: 'padding:1.5rem;text-align:center;color:var(--mut)' }, 'Loading audit history…'));
  try {
    const data = await api.get('/api/audit');
    const logs = data.items || [];

    const content = h('div', {},
      h('div', { class: 'card-header' },
        h('h3', { class: 'card-title' }, `Security & Mutation Audit Log (${logs.length} Records)`),
        h('span', { style: 'font-size:0.82rem;color:var(--mut);' }, 'Tamper-evident record of all changes')
      ),
      logs.length > 0 ? h('div', { class: 'tw' },
        h('table', {},
          h('thead', {},
            h('tr', {},
              h('th', {}, 'Timestamp'),
              h('th', {}, 'Operator'),
              h('th', {}, 'Action'),
              h('th', {}, 'Record Reference'),
              h('th', {}, 'Result Status')
            )
          ),
          h('tbody', {},
            ...logs.map(lg => h('tr', {},
              h('td', { style: 'font-size:0.82rem;color:var(--mut);' }, fdate(lg.timestamp ? lg.timestamp.split('T')[0] : '')),
              h('td', { style: 'font-weight:600;' }, lg.user || 'System'),
              h('td', {}, badge(lg.action || 'Mutation', 'grey')),
              h('td', {}, lg.target || '—'),
              h('td', {}, badge('Success', 'ok'))
            ))
          )
        )
      ) : empty('No mutations logged yet', 'Authorized employee edits, status changes, and setup runs will be recorded here.', '📜')
    );
    setKids(container, content);
  } catch (err) {
    setKids(container, empty('Error loading audit log', err.message, '⚠️'));
  }
}

export async function renderSync(main) {
  setKids(main, h('div', { style: 'padding:2rem;text-align:center;color:var(--mut)' }, 'Checking workbook connection and freshness…'));

  try {
    const syncStatus = await api.get('/api/sync/status');
    const isLive = syncStatus.live;

    const forceRefresh = async () => {
      try {
        await api.post('/api/sync/refresh', {});
        toast('Master workbook re-synced successfully', 'ok');
        renderSync(main);
      } catch (err) {
        toast(err.message || 'Refresh failed', 'bad');
      }
    };

    const content = h('div', {},
      h('div', { class: 'top' },
        h('div', { class: 'top-title' },
          h('h1', {}, 'Workbook Connection & Sync Health'),
          h('div', { class: 'sub' }, 'Truthful connection status, source freshness, and two-way sync diagnostics.')
        ),
        h('div', { class: 'top-actions' },
          h('button', { class: 'btn pri sm', onclick: forceRefresh }, '⟳ Refresh Master Now')
        )
      ),

      // Connection Status Card
      h('div', { class: 'card', style: 'margin-bottom:1.5rem;' },
        h('div', { class: 'card-header' },
          h('h3', { class: 'card-title' }, 'Active Data Source Diagnostic'),
          badge(isLive ? 'Live Microsoft 365' : 'Local Test Copy', isLive ? 'ok' : 'warn')
        ),
        h('div', { class: 'grid g3', style: 'margin-bottom:1.25rem;' },
          h('div', { class: 'stat-card' },
            h('div', { class: 'label' }, 'Connection State'),
            h('div', { class: 'val', style: 'font-size:1.45rem;' }, syncStatus.label || 'Connected'),
            h('div', { class: 'subtext' }, isLive ? 'Microsoft Graph API Active' : 'Operating on local disk copy')
          ),
          h('div', { class: 'stat-card' },
            h('div', { class: 'label' }, 'Last Successful Refresh'),
            h('div', { class: 'val', style: 'font-size:1.45rem;' }, syncStatus.last_success ? syncStatus.last_success.split('T')[1].slice(0, 5) : 'Just now'),
            h('div', { class: 'subtext' }, `Interval: Every ${syncStatus.interval_seconds || 30}s`)
          ),
          h('div', { class: 'stat-card' },
            h('div', { class: 'label' }, 'Master File Name'),
            h('div', { class: 'val', style: 'font-size:1.25rem;overflow:hidden;text-overflow:ellipsis;' }, syncStatus.file_name || 'test_workbook.xlsx'),
            h('div', { class: 'subtext' }, `Adapter: ${syncStatus.source ? syncStatus.source.adapter : 'local'}`)
          )
        ),
        !isLive ? h('div', { class: 'banner warn', style: 'margin-bottom:0;' },
          h('div', {},
            h('strong', {}, 'Notice: Local Development Mode'),
            h('div', { style: 'font-size:0.82rem;margin-top:0.2rem;' },
              'Changes saved here write to the local test copy on your computer. When you deploy with Microsoft Entra ID and Graph credentials, the app connects directly to your live OneDrive/SharePoint workbook.'
            )
          )
        ) : null
      ),

      // Production Go-Live Guide Callout
      h('div', { class: 'card' },
        h('div', { class: 'card-header' },
          h('h3', { class: 'card-title' }, 'Path to Live Microsoft 365 Production & Phone Access')
        ),
        h('div', { style: 'font-size:0.88rem;line-height:1.6;color:var(--ink);' },
          h('p', { style: 'margin-bottom:0.75rem;' },
            'To connect to your real Microsoft 365 workbook and access the app from your phone:'
          ),
          h('ol', { style: 'padding-left:1.5rem;margin-bottom:1rem;display:flex;flex-direction:column;gap:0.35rem;' },
            h('li', {}, 'Deploy backend to a secure host with HTTPS (e.g. Render, Railway, Azure App Service).'),
            h('li', {}, 'Register an App in Microsoft Entra ID with least-privilege Files.ReadWrite scope.'),
            h('li', {}, 'Set SOURCE=graph with your Azure Tenant ID, Client ID, Client Secret, Drive ID, and Item ID.'),
            h('li', {}, 'Open the deployed HTTPS URL on your phone (Safari on iOS or Chrome on Android).'),
            h('li', {}, 'Tap "Share" → "Add to Home Screen" to install the full PWA without an app store.')
          ),
          h('div', { style: 'font-size:0.82rem;color:var(--mut);' },
            'See docs/DEPLOYMENT_AND_MOBILE_GUIDE.md for complete step-by-step instructions.'
          )
        )
      )
    );

    setKids(main, content);
  } catch (err) {
    setKids(main, empty('Error loading sync status', err.message, '⚠️'));
  }
}
