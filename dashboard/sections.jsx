// sections.jsx — page-level views for each nav entry

const { KPI, Sparkline, AreaChart, ScoreBar, FwTag, ScoreNum } = window.NormaUI;
const Icon = window.NormaIcon;
const D = window.NormaData;

// ── Overview ──────────────────────────────────────────────────────

function roleKpis(role) {
  if (role === 'exec') return [
    { label: 'Compliance media',      value: '74',  unit: '%', trend: { dir: 'up',   text: '+3.1 vs trim. precedente' }, foot: '7 framework · 5 clienti', tint: 'radial-gradient(120% 80% at 100% 0%, rgba(91,140,255,.18), transparent 60%)', icon: 'target' },
    { label: 'Rischio aperto',        value: '€ 1.4', unit: 'M', trend: { dir: 'down', text: '−€ 220K dal mese scorso' }, foot: 'Esposizione stimata sanzioni', icon: 'shield' },
    { label: 'Deadline 90gg',         value: '18',           trend: { dir: 'flat', text: 'di cui 4 critiche' }, foot: 'Includendo trasposizioni nazionali', icon: 'pulse' },
    { label: 'Coverage corpus',       value: '99.2', unit: '%', trend: { dir: 'up',   text: '+412 articoli oggi' }, foot: 'EU + IT + 3 regulator', icon: 'graph' },
  ];
  if (role === 'consultant') return [
    { label: 'Clienti attivi',        value: '5',            trend: { dir: 'up',   text: '+1 questo mese' }, foot: '7 framework monitorati', tint: 'radial-gradient(120% 80% at 100% 0%, rgba(176,139,255,.18), transparent 60%)', icon: 'users' },
    { label: 'Q&A risolte oggi',      value: '47',           trend: { dir: 'up',   text: '+12% vs media' }, foot: '92% conf. media · 3 review', icon: 'spark' },
    { label: 'Gap aperti',            value: '94',           trend: { dir: 'down', text: '−18 questa settimana' }, foot: '12 critici · 31 alti', icon: 'target' },
    { label: 'Ore fatturabili / sett.', value: '36.5', unit: 'h', trend: { dir: 'up', text: '+4h vs target' }, foot: 'di cui 21h su NormaAI', icon: 'pulse' },
  ];
  // dpo
  return [
    { label: 'Compliance complessiva', value: '74', unit: '%', trend: { dir: 'up',   text: '+3.1 vs scorso mese' }, foot: '7 framework attivi', tint: 'radial-gradient(120% 80% at 100% 0%, rgba(91,140,255,.18), transparent 60%)', icon: 'target' },
    { label: 'Gap aperti',             value: '94',           trend: { dir: 'down', text: '−18 ultime 2 settimane' }, foot: '12 critici · 31 alti', icon: 'shield' },
    { label: 'Alert 7gg',              value: '23',           trend: { dir: 'up',   text: '+7 vs settimana scorsa' }, foot: '2 P0 · 9 P1 · 12 P2', icon: 'bell' },
    { label: 'Q&A corpus indicizzato', value: '128K', unit: 'chunk', trend: { dir: 'up', text: '+412 oggi' }, foot: 'EU + nazionali + soft-law', icon: 'graph' },
  ];
}

function OverviewSection({ role, framework, range }) {
  const fws = framework === 'ALL'
    ? D.FRAMEWORKS
    : D.FRAMEWORKS.filter(f => f.id === framework);

  return (
    <div>
      <div className="section-head">
        <div>
          <h2>Buongiorno, Marta.</h2>
          <p>Ecco lo stato compliance · range <strong className="mono">{range}</strong> · framework <strong>{framework === 'ALL' ? 'tutti' : framework}</strong>.</p>
        </div>
        <div className="section-actions">
          <button className="btn ghost"><Icon name="report" size={14} /> Esporta board pack</button>
          <button className="btn"><Icon name="sliders" size={14} /> Personalizza</button>
        </div>
      </div>

      <div className="kpi-grid">
        {roleKpis(role).map((k, i) => <KPI key={i} {...k} />)}
      </div>

      {/* Compliance per framework */}
      <div className="row-2">
        <div className="card">
          <div className="card-head">
            <h3>Compliance per framework</h3>
            <span className="card-sub">stato vs target · {fws.length} framework</span>
            <div className="card-actions">
              <span className="tag good">●  buono ≥ 80</span>
              <span className="tag warn">●  attenzione 60–79</span>
              <span className="tag bad">●  critico &lt; 60</span>
            </div>
          </div>
          <div>
            <div className="fw-row head">
              <span>Framework</span><span>Score</span><span>Avanzamento vs target</span>
              <span style={{ textAlign: 'right' }}>Articoli</span>
              <span style={{ textAlign: 'right' }}>Gap</span>
              <span style={{ textAlign: 'right' }}>Owner</span>
            </div>
            {fws.map(f => (
              <div key={f.id} className="fw-row" style={{ '--fw-color': f.color }}>
                <span className="fw-name"><span className="fw-dot" />{f.name}</span>
                <ScoreNum v={f.score} />
                <div>
                  <ScoreBar value={f.score} color={f.color} />
                  <div className="tiny mute2 mono" style={{ marginTop: 4 }}>
                    target {f.target}% · gap {f.target - f.score}pt
                  </div>
                </div>
                <span className="cell-mute" style={{ textAlign: 'right' }}>{f.articles}</span>
                <span className="cell-mute" style={{ textAlign: 'right' }}>
                  {f.gaps > 0
                    ? <span className={f.gaps > 15 ? 'tag bad' : f.gaps > 8 ? 'tag warn' : 'tag good'}>{f.gaps}</span>
                    : <span className="tag good">0</span>}
                </span>
                <span className="cell-mute mono" style={{ textAlign: 'right' }}>{f.owner}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>Prossime scadenze</h3>
            <span className="card-sub">5 / 18 totali</span>
            <div className="card-actions">
              <button className="btn ghost btn-icon"><Icon name="arrow" size={14} /></button>
            </div>
          </div>
          <div>
            {D.DEADLINES.map((dl, i) => (
              <div key={i} className="deadline">
                <div className="deadline-date">
                  <div className="d">{dl.d}</div>
                  <div className="m">{dl.m} {String(dl.y).slice(-2)}</div>
                </div>
                <div>
                  <div className="deadline-title">{dl.title}</div>
                  <div className="deadline-sub"><FwTag id={dl.fw} /> &nbsp;{dl.sub}</div>
                </div>
                <div className="deadline-rt">
                  <span className={`tag ${dl.tone}`}>−{dl.left}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Volume Q&A + alert + activity */}
      <div className="row-2">
        <div className="card">
          <div className="card-head">
            <h3>Volume Q&A normativo</h3>
            <span className="card-sub">richieste / giorno · {range}</span>
            <div className="card-actions">
              <span className="tag info">media 84/g</span>
              <span className="tag good">latenza p95 1.2s</span>
            </div>
          </div>
          <div className="card-pad">
            <AreaChart data={D.SPARK_REQUESTS} />
            <div className="spread tiny mute2" style={{ marginTop: 6 }}>
              <span>30 giorni fa</span>
              <span>oggi · 131 richieste</span>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>Alert prioritari</h3>
            <span className="card-sub">P0 + P1</span>
            <div className="card-actions">
              <button className="btn ghost">Tutti</button>
            </div>
          </div>
          <div className="list">
            {D.ALERTS.slice(0, 5).map((a, i) => (
              <div key={i} className="list-row">
                <span className={`priority ${a.p}`} title={a.p.toUpperCase()} />
                <div>
                  <div className="list-title">{a.title}</div>
                  <div className="meta"><FwTag id={a.fw} /> · {a.src} · impatto {a.impact}</div>
                </div>
                <time>{a.ts}</time>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="row-12">
        <div className="card">
          <div className="card-head">
            <h3>Q&A recenti</h3>
            <span className="card-sub">grounded sul corpus</span>
          </div>
          <div className="list">
            {D.QA_RECENT.map((q, i) => (
              <div key={i} className="list-row">
                <Icon name="spark" size={14} />
                <div>
                  <div className="list-title">{q.q}</div>
                  <div className="meta"><FwTag id={q.fw} /> · {q.user} · conf. <span className="mono">{q.conf}%</span></div>
                </div>
                <time>{q.ts}</time>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>Attività team</h3>
            <span className="card-sub">live · ultime 6h</span>
          </div>
          <div className="list">
            {D.ACTIVITY.map((a, i) => (
              <div key={i} className="list-row">
                <span className={`priority p${a.tone === 'good' ? 2 : a.tone === 'warn' ? 1 : 3}`} />
                <div>
                  <div className="list-title">
                    <strong style={{ fontWeight: 600 }}>{a.who}</strong> <span className="muted">{a.what}</span> · {a.on}
                  </div>
                  <div className="meta">{a.tone === 'good' ? 'Completato' : a.tone === 'warn' ? 'Da rivedere' : 'Info'}</div>
                </div>
                <time>{a.when}</time>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Generic placeholders for the other views ─────────────────────

function SectionShell({ title, sub, children }) {
  return (
    <div>
      <div className="section-head">
        <div><h2>{title}</h2><p>{sub}</p></div>
      </div>
      {children}
    </div>
  );
}

function QASection() {
  return (
    <SectionShell title="Q&A normativo" sub="Domande grounded · risposta con citazioni">
      <div className="card card-pad" style={{ marginBottom: 14 }}>
        <div className="row" style={{ alignItems: 'flex-start', gap: 12 }}>
          <Icon name="spark" />
          <textarea
            placeholder="Es. Quali soglie applicano a una holding non quotata sotto CSRD?"
            style={{ flex: 1, minHeight: 70, background: 'transparent', border: 'none', outline: 'none', color: 'var(--ink)', fontFamily: 'inherit', fontSize: 14, resize: 'vertical' }}
            defaultValue="Obblighi due diligence per fornitori Tier 2 fuori UE — quando scattano sotto CSDDD?"
          />
          <button className="btn primary">Chiedi</button>
        </div>
        <div className="divider" />
        <div className="tiny muted">Risposta · CSDDD Art. 8(2) · 4 fonti citate · conf. 88%</div>
        <p style={{ fontSize: 14, lineHeight: 1.6, margin: '8px 0 0' }}>
          La direttiva impone agli operatori in scope di identificare e prevenire impatti
          avversi anche oltre i fornitori Tier 1 quando esistono <em>prove ragionevoli</em>
          che il rischio si concretizzi nella catena del valore. Per Tier 2 fuori UE l’obbligo
          scatta in presenza di indicatori sintetici di rischio (paese, settore, prodotto)
          documentati nella value chain mapping.
        </p>
        <div className="row" style={{ marginTop: 10, flexWrap: 'wrap', gap: 6 }}>
          <span className="tag fw" style={{ '--fw-color': 'var(--fw-csddd)' }}>CSDDD Art. 8</span>
          <span className="tag">Considerando 30</span>
          <span className="tag">EFRAG QA #418</span>
          <span className="tag">Linee guida 2025/C 14</span>
        </div>
      </div>

      <div className="card">
        <div className="card-head"><h3>Cronologia Q&A</h3><span className="card-sub">team</span></div>
        <table className="tbl">
          <thead><tr><th>Domanda</th><th>Framework</th><th>Utente</th><th>Conf.</th><th>Quando</th></tr></thead>
          <tbody>
            {D.QA_RECENT.map((q, i) => (
              <tr key={i}>
                <td>{q.q}</td>
                <td><FwTag id={q.fw} /></td>
                <td className="muted">{q.user}</td>
                <td className="num">{q.conf}%</td>
                <td className="muted">{q.ts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionShell>
  );
}

function GapSection({ framework }) {
  const fws = framework === 'ALL' ? D.FRAMEWORKS : D.FRAMEWORKS.filter(f => f.id === framework);
  return (
    <SectionShell title="Gap analysis" sub="Articoli, requisiti e azioni mancanti">
      <div className="kpi-grid">
        <KPI label="Gap totali" value="94" foot="su 7 framework" icon="target" />
        <KPI label="Critici (P0)" value="12" trend={{dir:'down', text:'−3 sett.'}} icon="shield" />
        <KPI label="Risolti 30g" value="38" trend={{dir:'up', text:'+18%'}} icon="pulse" />
        <KPI label="Tempo medio chiusura" value="11" unit="g" icon="graph" />
      </div>
      <div className="card">
        <div className="card-head"><h3>Distribuzione gap per framework</h3></div>
        <table className="tbl">
          <thead><tr><th>Framework</th><th>Score</th><th>P0</th><th>P1</th><th>P2</th><th>Owner</th><th>SLA medio</th></tr></thead>
          <tbody>
            {fws.map(f => (
              <tr key={f.id}>
                <td><FwTag id={f.id} /> <span className="muted" style={{ marginLeft: 6 }}>{f.label}</span></td>
                <td><ScoreNum v={f.score} /></td>
                <td className="num"><span className="tag bad">{Math.max(1, Math.round(f.gaps * 0.18))}</span></td>
                <td className="num"><span className="tag warn">{Math.round(f.gaps * 0.42)}</span></td>
                <td className="num"><span className="tag info">{Math.round(f.gaps * 0.40)}</span></td>
                <td className="muted">{f.owner}</td>
                <td className="num muted">{8 + (f.gaps % 9)} g</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionShell>
  );
}

function MonitorSection() {
  return (
    <SectionShell title="Change monitor" sub="Variazioni testuali rilevate sulle fonti ufficiali · diff e versioning">
      <div className="card">
        <div className="card-head"><h3>Sorgenti monitorate</h3><span className="card-sub">{D.MONITOR.length} feed</span></div>
        <table className="tbl">
          <thead><tr><th>Sorgente</th><th>Match 24h</th><th>Δ vs media</th><th>Ultimo poll</th><th>Stato</th></tr></thead>
          <tbody>
            {D.MONITOR.map((m, i) => (
              <tr key={i}>
                <td>{m.src}</td>
                <td className="num">{m.hits}</td>
                <td className="num"><span className={m.delta.startsWith('+') ? 'tag good' : 'tag warn'}>{m.delta}</span></td>
                <td className="muted">{m.last}</td>
                <td><span className={`tag ${m.health}`}>{m.health === 'good' ? 'OK' : 'rallentato'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionShell>
  );
}

function CrossSection() {
  return (
    <SectionShell title="Cross-framework intelligence" sub="Doppi obblighi, sovrapposizioni, conflitti tra norme">
      <div className="card card-pad">
        <p className="muted">Matrice di interconnessione — placeholder. Ogni cella mostra n. requisiti condivisi (es. <span className="mono">DORA × NIS2 = 14</span>).</p>
        <div style={{ display: 'grid', gridTemplateColumns: '120px repeat(7, 1fr)', gap: 4, marginTop: 14, fontSize: 11 }}>
          <div></div>
          {D.FRAMEWORKS.map(f => <div key={f.id} className="muted" style={{ textAlign: 'center' }}>{f.name}</div>)}
          {D.FRAMEWORKS.map((row, ri) => (
            <React.Fragment key={row.id}>
              <div className="muted" style={{ paddingRight: 8, textAlign: 'right' }}>{row.name}</div>
              {D.FRAMEWORKS.map((col, ci) => {
                if (ri === ci) return <div key={col.id} style={{ background: 'var(--surface-2)', height: 36, borderRadius: 4 }} />;
                const v = ((ri + 1) * (ci + 3)) % 22;
                const intensity = v / 22;
                return (
                  <div key={col.id} style={{
                    height: 36, borderRadius: 4,
                    background: `color-mix(in oklab, var(--accent) ${intensity * 70}%, var(--surface))`,
                    color: intensity > 0.4 ? '#fff' : 'var(--ink-3)',
                    display: 'grid', placeItems: 'center', fontFamily: 'Geist Mono', fontSize: 11,
                  }}>{v}</div>
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </div>
    </SectionShell>
  );
}

function AlertsSection() {
  return (
    <SectionShell title="Alert" sub="Notifiche prioritarie · da triage · backlog 30g">
      <div className="card">
        <div className="card-head">
          <h3>Coda alert</h3>
          <div className="card-actions">
            <button className="btn ghost">P0 (2)</button>
            <button className="btn ghost">P1 (9)</button>
            <button className="btn ghost">P2 (12)</button>
          </div>
        </div>
        <table className="tbl">
          <thead><tr><th></th><th>Titolo</th><th>Framework</th><th>Sorgente</th><th>Impatto</th><th>Quando</th></tr></thead>
          <tbody>
            {D.ALERTS.map((a, i) => (
              <tr key={i}>
                <td><span className={`priority ${a.p}`} /></td>
                <td>{a.title}</td>
                <td><FwTag id={a.fw} /></td>
                <td className="muted">{a.src}</td>
                <td><span className={a.impact === 'Alto' ? 'tag bad' : a.impact === 'Medio' ? 'tag warn' : 'tag info'}>{a.impact}</span></td>
                <td className="muted">{a.ts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionShell>
  );
}

function FeedSection() {
  return (
    <SectionShell title="Regulatory feed" sub="Flusso normativo aggregato · classificato · diff-aware">
      <div className="card">
        <div className="list">
          {D.ALERTS.concat(D.ALERTS).slice(0, 9).map((a, i) => (
            <div key={i} className="list-row">
              <Icon name="feed" size={14} />
              <div>
                <div className="list-title">{a.title}</div>
                <div className="meta"><FwTag id={a.fw} /> · {a.src} · impatto {a.impact}</div>
              </div>
              <time>{a.ts}</time>
            </div>
          ))}
        </div>
      </div>
    </SectionShell>
  );
}

function DocumentsSection() {
  const rows = [
    { name: 'Policy AI governance v3.2.pdf',     fw: 'AI_ACT', size: '2.4 MB', up: '2g fa', owner: 'Marta R.', kind: 'Policy' },
    { name: 'Procedura incident NIS2.docx',      fw: 'NIS2',   size: '186 KB', up: '5g fa', owner: 'CISO',     kind: 'Procedura' },
    { name: 'TIA Q4 2026 — clienti EU.xlsx',     fw: 'GDPR',   size: '910 KB', up: '1g fa', owner: 'DPO',      kind: 'Evidenza' },
    { name: 'Mappatura value chain Tier1.csv',   fw: 'CSDDD',  size: '4.1 MB', up: '8g fa', owner: 'Davide T.',kind: 'Dataset' },
  ];
  return (
    <SectionShell title="Documenti" sub="Policy, procedure, evidenze · indicizzati nel corpus">
      <div className="card">
        <table className="tbl">
          <thead><tr><th>Nome</th><th>Tipo</th><th>Framework</th><th>Owner</th><th>Dim.</th><th>Aggiornato</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><Icon name="doc" size={14} /> <span style={{ marginLeft: 8 }}>{r.name}</span></td>
                <td className="muted">{r.kind}</td>
                <td><FwTag id={r.fw} /></td>
                <td className="muted">{r.owner}</td>
                <td className="num muted">{r.size}</td>
                <td className="muted">{r.up}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionShell>
  );
}

function ReportsSection() {
  const reports = [
    { title: 'Board pack Q4 2026',  fw: 'multi', who: 'Generato', when: 'oggi 09:12', kind: 'PDF' },
    { title: 'CSRD ESRS S1 — bozza', fw: 'CSRD', who: 'Marta R.', when: 'ieri',       kind: 'DOCX' },
    { title: 'DORA TLPT plan',       fw: 'DORA', who: 'CISO',     when: '3g fa',      kind: 'PDF'  },
    { title: 'GDPR — TIA Q4',        fw: 'GDPR', who: 'DPO',      when: '5g fa',      kind: 'XLSX' },
  ];
  return (
    <SectionShell title="Report" sub="Board, autorità, audit · template + generazione AI-assistita">
      <div className="kpi-grid">
        <KPI label="Generati YTD" value="42" trend={{dir:'up', text:'+9 trim.'}} icon="report" />
        <KPI label="In bozza"     value="6"                                       icon="doc" />
        <KPI label="Approvati"    value="31"                                      icon="shield" />
        <KPI label="Tempo medio gen." value="3.4" unit="min"                      icon="pulse" />
      </div>
      <div className="card">
        <table className="tbl">
          <thead><tr><th>Titolo</th><th>Framework</th><th>Formato</th><th>Owner</th><th>Quando</th><th></th></tr></thead>
          <tbody>
            {reports.map((r, i) => (
              <tr key={i}>
                <td>{r.title}</td>
                <td>{r.fw === 'multi' ? <span className="tag info">multi-fw</span> : <FwTag id={r.fw} />}</td>
                <td className="mono muted">{r.kind}</td>
                <td className="muted">{r.who}</td>
                <td className="muted">{r.when}</td>
                <td style={{ textAlign: 'right' }}><button className="btn ghost btn-icon"><Icon name="arrow" size={14} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionShell>
  );
}

function ClientsSection() {
  return (
    <SectionShell title="Clienti" sub="Tenant · scope di compliance · owner">
      <div className="row-3">
        {D.CLIENTS.map((c, i) => (
          <div key={i} className="card card-pad">
            <div className="spread">
              <strong>{c.name}</strong>
              <span className={c.risk === 'Alto' ? 'tag bad' : c.risk === 'Medio' ? 'tag warn' : 'tag good'}>{c.risk}</span>
            </div>
            <div className="tiny muted" style={{ marginTop: 4 }}>{c.sector} · {c.size}</div>
            <div className="row" style={{ marginTop: 14, gap: 10 }}>
              <ScoreNum v={c.score} />
              <div style={{ flex: 1 }}><ScoreBar value={c.score} color="var(--accent)" /></div>
            </div>
            <div className="row" style={{ flexWrap: 'wrap', marginTop: 12, gap: 5 }}>
              {c.fws.map(fw => <FwTag key={fw} id={fw} />)}
            </div>
          </div>
        ))}
      </div>
    </SectionShell>
  );
}

function AuditSection() {
  const rows = D.ACTIVITY.concat(D.ACTIVITY).slice(0, 10);
  return (
    <SectionShell title="Audit trail" sub="Tracciatura immutabile · azioni utenti, dataset, modelli">
      <div className="card">
        <table className="tbl">
          <thead><tr><th>Quando</th><th>Attore</th><th>Azione</th><th>Oggetto</th><th>Hash</th></tr></thead>
          <tbody>
            {rows.map((a, i) => (
              <tr key={i}>
                <td className="mono muted">2026-04-27 {a.when}</td>
                <td>{a.who}</td>
                <td className="muted">{a.what}</td>
                <td>{a.on}</td>
                <td className="mono mute2 tiny">a8f3…{(i*7919).toString(16).slice(-4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionShell>
  );
}

function WorkflowSection() {
  const cols = [
    { title: 'Backlog',   tone: 'info', cards: [
      { t: 'Aggiornare TIA fornitori cloud', fw: 'GDPR', who: 'DPO',   p: 'p2' },
      { t: 'Mappare ESRS S1 KPIs',           fw: 'CSRD', who: 'Marta', p: 'p1' },
    ]},
    { title: 'In corso',  tone: 'warn', cards: [
      { t: 'Risposta a EFRAG QA #418',       fw: 'CSRD', who: 'Marta', p: 'p1' },
      { t: 'Test TLPT — kick-off vendor',    fw: 'DORA', who: 'CISO',  p: 'p1' },
      { t: 'Value chain Tier 2 cleanup',     fw: 'CSDDD',who: 'Davide',p: 'p0' },
    ]},
    { title: 'Review',    tone: 'info', cards: [
      { t: 'Policy AI governance v3.2',      fw: 'AI_ACT', who: 'Comitato', p: 'p1' },
    ]},
    { title: 'Done',      tone: 'good', cards: [
      { t: 'Notifica incidenti NIS2 v1',     fw: 'NIS2', who: 'CISO', p: 'p2' },
      { t: 'Indicizzazione ESRS allegati',   fw: 'CSRD', who: 'AI',   p: 'p3' },
    ]},
  ];
  return (
    <SectionShell title="Workflow" sub="Task, approvazioni, owner · SLA visibili">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        {cols.map((c, i) => (
          <div key={i} className="card">
            <div className="card-head">
              <h3>{c.title}</h3>
              <span className="card-sub">{c.cards.length}</span>
            </div>
            <div style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {c.cards.map((k, j) => (
                <div key={j} style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 10,
                  padding: 10,
                }}>
                  <div className="tiny muted" style={{ marginBottom: 4 }}>
                    <span className={`priority ${k.p}`} /> <FwTag id={k.fw} />
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.35 }}>{k.t}</div>
                  <div className="tiny mute2" style={{ marginTop: 6 }}>{k.who}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </SectionShell>
  );
}

function AnalyticsSection() {
  return (
    <SectionShell title="Analytics" sub="Utilizzo, latenza, qualità retrieval">
      <div className="kpi-grid">
        <KPI label="Richieste 30g" value="2'418" trend={{dir:'up', text:'+24%'}} icon="pulse" />
        <KPI label="Latenza p95" value="1.18" unit="s" trend={{dir:'down', text:'−180ms'}} icon="graph" />
        <KPI label="Recall@5" value="93.2" unit="%" trend={{dir:'up', text:'+1.4pt'}} icon="target" />
        <KPI label="Costo / Q&A" value="€ 0.034" trend={{dir:'down', text:'−€ 0.008'}} icon="report" />
      </div>
      <div className="card">
        <div className="card-head"><h3>Volume richieste</h3><span className="card-sub">30g</span></div>
        <div className="card-pad"><AreaChart data={D.SPARK_REQUESTS} /></div>
      </div>
    </SectionShell>
  );
}

function AdminSection() {
  return (
    <SectionShell title="Amministrazione" sub="Utenti, ruoli, integrazioni, modelli">
      <div className="row-3">
        <div className="card card-pad">
          <h3 style={{ margin: '0 0 8px' }}>Modello LLM</h3>
          <div className="mono tiny mute2">claude-sonnet-4.5</div>
          <div className="tiny muted" style={{ marginTop: 8 }}>Provider Anthropic · region EU-FR</div>
          <div className="row" style={{ gap: 6, marginTop: 10 }}>
            <span className="tag good">Online</span>
            <span className="tag info">Sovereign</span>
          </div>
        </div>
        <div className="card card-pad">
          <h3 style={{ margin: '0 0 8px' }}>Vector DB</h3>
          <div className="mono tiny mute2">qdrant · 128.418 chunk</div>
          <div className="tiny muted" style={{ marginTop: 8 }}>Embedding multilingual-e5</div>
          <div className="row" style={{ gap: 6, marginTop: 10 }}>
            <span className="tag good">OK</span>
            <span className="tag info">5 collection</span>
          </div>
        </div>
        <div className="card card-pad">
          <h3 style={{ margin: '0 0 8px' }}>Utenti</h3>
          <div className="mono tiny mute2">14 attivi · 3 invitati</div>
          <div className="tiny muted" style={{ marginTop: 8 }}>SSO via SAML · MFA obbligatorio</div>
          <div className="row" style={{ gap: 6, marginTop: 10 }}>
            <span className="tag good">SSO ok</span>
            <span className="tag info">RBAC</span>
          </div>
        </div>
      </div>
    </SectionShell>
  );
}

Object.assign(window, {
  OverviewSection, QASection, GapSection, MonitorSection, CrossSection,
  AlertsSection, FeedSection, DocumentsSection, ReportsSection, ClientsSection,
  AuditSection, WorkflowSection, AnalyticsSection, AdminSection,
});
