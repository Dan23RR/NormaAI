// chrome.jsx — Sidebar + Topbar for NormaAI dashboard

const NAV = [
  { group: 'Operatività', items: [
    { id: 'overview', label: 'Panoramica',          icon: 'grid' },
    { id: 'qa',       label: 'Q&A normativo',       icon: 'spark' },
    { id: 'gap',      label: 'Gap analysis',        icon: 'target' },
    { id: 'monitor',  label: 'Change monitor',      icon: 'pulse', badge: { text: '3', kind: 'warn' } },
    { id: 'cross',    label: 'Cross-framework',     icon: 'graph' },
  ]},
  { group: 'Avvisi', items: [
    { id: 'alerts',   label: 'Alert',               icon: 'bell',   badge: { text: '7', kind: 'bad' } },
    { id: 'feed',     label: 'Regulatory feed',     icon: 'feed' },
  ]},
  { group: 'Asset', items: [
    { id: 'documents', label: 'Documenti',          icon: 'doc' },
    { id: 'reports',   label: 'Report',             icon: 'report' },
    { id: 'clients',   label: 'Clienti',            icon: 'users' },
  ]},
  { group: 'Compliance', items: [
    { id: 'audit',     label: 'Audit trail',        icon: 'shield' },
    { id: 'workflow',  label: 'Workflow',           icon: 'flow' },
    { id: 'analytics', label: 'Analytics',          icon: 'chart' },
    { id: 'admin',     label: 'Amministrazione',    icon: 'cog' },
  ]},
];

const ROLE_LABELS = {
  dpo:        { name: 'Marta Rossi',     sub: 'DPO · Banca Adriatica' },
  consultant: { name: 'Davide Tessarin', sub: 'Senior consultant'      },
  exec:       { name: 'Francesca P.',    sub: 'Chief Compliance'       },
};

// Inline SVG icon set — keeps no external deps
function Icon({ name, size = 16 }) {
  const s = size;
  const p = { width: s, height: s, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round' };
  switch (name) {
    case 'grid':   return <svg {...p}><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>;
    case 'spark':  return <svg {...p}><path d="M12 3l2.2 5.4L20 10l-4.5 3.5L17 20l-5-3-5 3 1.5-6.5L4 10l5.8-1.6L12 3z"/></svg>;
    case 'target': return <svg {...p}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></svg>;
    case 'pulse':  return <svg {...p}><path d="M3 12h4l2-6 4 12 2-6h6"/></svg>;
    case 'graph':  return <svg {...p}><circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="7" r="2.5"/><circle cx="7" cy="18" r="2.5"/><circle cx="17" cy="17" r="2.5"/><path d="M8 7l8 0M7.5 8l9 8.5M8 17l8-1"/></svg>;
    case 'bell':   return <svg {...p}><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2.5h-15L6 16z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>;
    case 'feed':   return <svg {...p}><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1.5"/></svg>;
    case 'doc':    return <svg {...p}><path d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5"/><path d="M9 14h7M9 17h5"/></svg>;
    case 'report': return <svg {...p}><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>;
    case 'users':  return <svg {...p}><circle cx="9" cy="9" r="3.2"/><path d="M3 19c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><circle cx="17" cy="8" r="2.5"/><path d="M14.5 13.8c2 .3 6.5 1.4 6.5 5.2"/></svg>;
    case 'shield': return <svg {...p}><path d="M12 3l8 3v6c0 4.5-3.4 8.4-8 9-4.6-.6-8-4.5-8-9V6l8-3z"/><path d="M9 12l2 2 4-4"/></svg>;
    case 'flow':   return <svg {...p}><rect x="3"  y="4" width="6" height="5" rx="1"/><rect x="15" y="4" width="6" height="5" rx="1"/><rect x="9"  y="15" width="6" height="5" rx="1"/><path d="M6 9v3h12V9M12 12v3"/></svg>;
    case 'chart':  return <svg {...p}><path d="M4 20V8M10 20v-7M16 20v-4M22 20H2"/></svg>;
    case 'cog':    return <svg {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>;
    case 'search': return <svg {...p}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>;
    case 'plus':   return <svg {...p}><path d="M12 5v14M5 12h14"/></svg>;
    case 'sun':    return <svg {...p}><circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/></svg>;
    case 'help':   return <svg {...p}><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.5V14"/><circle cx="12" cy="17" r=".8" fill="currentColor"/></svg>;
    case 'sliders':return <svg {...p}><path d="M4 7h12M4 17h7"/><circle cx="18" cy="7" r="2"/><circle cx="14" cy="17" r="2"/></svg>;
    case 'chev':   return <svg {...p}><path d="m6 9 6 6 6-6"/></svg>;
    case 'arrow':  return <svg {...p}><path d="M5 12h14M13 6l6 6-6 6"/></svg>;
    case 'caret-l':return <svg {...p}><path d="m15 18-6-6 6-6"/></svg>;
    case 'caret-r':return <svg {...p}><path d="m9 6 6 6-6 6"/></svg>;
    default: return null;
  }
}

function NormaSidebar({ active, onNav, collapsed, onToggle, role }) {
  const u = ROLE_LABELS[role] || ROLE_LABELS.dpo;
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`} aria-label="Navigazione principale">
      <div className="brand">
        <div className="brand-mark">N</div>
        <div className="brand-text">
          <div className="brand-name">NormaAI</div>
          <div className="brand-sub">EU regulatory copilot</div>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', paddingBottom: 12 }}>
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="nav-group"><span className="nav-group-text">{g.group}</span></div>
            <ul className="nav-list">
              {g.items.map((it) => (
                <li key={it.id}>
                  <button
                    className={`nav-item ${active === it.id ? 'active' : ''}`}
                    onClick={() => onNav(it.id)}
                    title={collapsed ? it.label : undefined}
                  >
                    <span className="nav-icon"><Icon name={it.icon} /></span>
                    <span className="nav-label">{it.label}</span>
                    {it.badge && <span className={`nav-badge ${it.badge.kind}`}>{it.badge.text}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="sidebar-foot">
        <div className="user-card">
          <div className="avatar">{u.name.split(' ').map(s=>s[0]).slice(0,2).join('')}</div>
          <div className="user-text" style={{ minWidth: 0 }}>
            <div className="user-name" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{u.name}</div>
            <div className="user-role" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{u.sub}</div>
          </div>
        </div>
        <button className="collapse-btn" onClick={onToggle} aria-label="Restringi sidebar">
          <Icon name={collapsed ? 'caret-r' : 'caret-l'} size={14} />
          {!collapsed && <span style={{ marginLeft: 8, fontSize: 11 }}>Comprimi</span>}
        </button>
      </div>
    </aside>
  );
}

const TITLES = {
  overview:  ['Panoramica',          'Stato compliance multi-framework in tempo reale'],
  qa:        ['Q&A normativo',       'Domande grounded sul corpus EU + nazionale'],
  gap:       ['Gap analysis',        'Articoli, requisiti e azioni mancanti'],
  monitor:   ['Change monitor',      'Variazioni testuali rilevate sulle fonti ufficiali'],
  cross:     ['Cross-framework',     'Interconnessioni e doppi obblighi'],
  alerts:    ['Alert',               'Notifiche prioritarie e da triage'],
  feed:      ['Regulatory feed',     'Flusso normativo aggregato e classificato'],
  documents: ['Documenti',           'Policy, procedure, evidenze caricate'],
  reports:   ['Report',              'Report board, audit, autorità di vigilanza'],
  clients:   ['Clienti',             'Tenant, scope di compliance, owner'],
  audit:     ['Audit trail',         'Tracciatura azioni, dataset e modelli'],
  workflow:  ['Workflow',            'Task, approvazioni, owner e SLA'],
  analytics: ['Analytics',           'Utilizzo, latenza, qualità retrieval'],
  admin:     ['Amministrazione',     'Utenti, ruoli, integrazioni, modelli'],
};

function NormaTopbar({ active, role, framework, onFramework, range, onRange, client, onClient }) {
  const [t, sub] = TITLES[active] || ['Dashboard', ''];
  return (
    <header className="topbar" role="banner">
      <div className="crumb">
        <span>NormaAI</span> <span style={{ color: 'var(--ink-4)', margin: '0 6px' }}>/</span>
        <strong>{t}</strong>
        <span style={{ color: 'var(--ink-4)', marginLeft: 10 }}>·</span>
        <span style={{ marginLeft: 10 }}>{sub}</span>
      </div>

      <div className="search">
        <Icon name="search" size={14} />
        <input placeholder="Cerca articoli, clienti, ticket… (es. ‘ESRS E1 Scope 3’)" />
        <span className="kbd">⌘K</span>
      </div>

      <div className="top-actions">
        <label className="chip-select">
          <span style={{ color: 'var(--ink-4)', fontSize: 11 }}>Cliente</span>
          <select value={client} onChange={(e) => onClient(e.target.value)}>
            <option value="ALL">Tutti</option>
            <option value="BANCA">Banca Adriatica</option>
            <option value="ACC">Acciaierie Norditalia</option>
            <option value="MED">MedTech Lombarda</option>
          </select>
        </label>
        <label className="chip-select">
          <span style={{ color: 'var(--ink-4)', fontSize: 11 }}>Range</span>
          <select value={range} onChange={(e) => onRange(e.target.value)}>
            <option value="7g">7 g</option>
            <option value="30g">30 g</option>
            <option value="90g">90 g</option>
            <option value="YTD">YTD</option>
          </select>
        </label>
        <button className="icon-btn" aria-label="Notifiche"><Icon name="bell" /><span className="dot" /></button>
        <button className="icon-btn" aria-label="Aiuto"><Icon name="help" /></button>
        <button className="btn primary"><Icon name="plus" size={14} /> Nuova analisi</button>
      </div>
    </header>
  );
}

window.NormaSidebar = NormaSidebar;
window.NormaTopbar = NormaTopbar;
window.NormaIcon = Icon;
