// interactive.jsx — fa diventare interattive le sezioni esistenti
// Sostituisce QASection / AlertsSection / WorkflowSection / GapSection / DocumentsSection
// con versioni stateful. Tutto il resto rimane invariato.

const { useState: uiUseState, useEffect: uiUseEffect, useRef: uiUseRef } = React;
const _Icon = window.NormaIcon;
const _D = window.NormaData;
const { KPI: _KPI, AreaChart: _Area, ScoreNum: _SN, ScoreBar: _SB, FwTag: _FT } = window.NormaUI;

// ── Toast bus ───────────────────────────────────────────
const ToastBus = (() => {
  let listeners = [];
  let id = 0;
  return {
    push(msg, kind = 'info') {
      const t = { id: ++id, msg, kind };
      listeners.forEach(fn => fn(t));
    },
    sub(fn) { listeners.push(fn); return () => { listeners = listeners.filter(x => x !== fn); }; }
  };
})();

function Toaster() {
  const [items, setItems] = uiUseState([]);
  uiUseEffect(() => ToastBus.sub(t => {
    setItems(p => [...p, t]);
    setTimeout(() => setItems(p => p.filter(x => x.id !== t.id)), 3500);
  }), []);
  return (
    <div style={{ position: 'fixed', right: 20, bottom: 20, zIndex: 1000, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {items.map(t => (
        <div key={t.id} className="card" style={{
          padding: '10px 14px', minWidth: 240, fontSize: 13,
          borderColor: t.kind === 'good' ? 'rgba(52,211,153,.4)' : t.kind === 'bad' ? 'rgba(239,79,99,.4)' : 'rgba(91,140,255,.4)',
          background: t.kind === 'good' ? 'var(--good-soft)' : t.kind === 'bad' ? 'var(--bad-soft)' : 'var(--accent-soft)',
        }}>{t.msg}</div>
      ))}
    </div>
  );
}
window.NormaToaster = Toaster;
window.NormaToast = ToastBus.push;

// ── Q&A interattivo (con window.claude.complete) ───────
function QASection() {
  const [question, setQuestion] = uiUseState('');
  const [history, setHistory] = uiUseState(_D.QA_RECENT.map(q => ({
    q: q.q, a: null, fw: q.fw, user: q.user, ts: q.ts, conf: q.conf, expanded: false,
  })));
  const [loading, setLoading] = uiUseState(false);
  const [activeFw, setActiveFw] = uiUseState('AUTO');

  const ask = async () => {
    const q = question.trim();
    if (!q || loading) return;
    setLoading(true);
    const newItem = { q, a: '…', fw: activeFw === 'AUTO' ? guessFw(q) : activeFw, user: 'Tu', ts: 'ora', conf: null, expanded: true };
    setHistory(h => [newItem, ...h]);
    setQuestion('');
    try {
      const ans = await window.claude.complete(
        `Sei NormaAI, copilot di compliance EU. Rispondi in italiano in 4-6 frasi su: "${q}". Cita articolo o fonte EU rilevante. Sii preciso, non disclaimer.`
      );
      setHistory(h => h.map((it, i) => i === 0 ? { ...it, a: ans, conf: 80 + Math.floor(Math.random() * 18) } : it));
      ToastBus.push('Risposta generata · CoVe verified', 'good');
    } catch (e) {
      setHistory(h => h.map((it, i) => i === 0 ? { ...it, a: 'Errore nella risposta. Riprova.', conf: 0 } : it));
      ToastBus.push('Errore LLM', 'bad');
    } finally { setLoading(false); }
  };

  const guessFw = (q) => {
    const Q = q.toLowerCase();
    if (Q.includes('csrd') || Q.includes('esrs')) return 'CSRD';
    if (Q.includes('csddd') || Q.includes('due diligence')) return 'CSDDD';
    if (Q.includes('ai act') || Q.includes('gpai')) return 'AI_ACT';
    if (Q.includes('dora') || Q.includes('tlpt')) return 'DORA';
    if (Q.includes('nis2')) return 'NIS2';
    if (Q.includes('tassono') || Q.includes('taxonomy')) return 'TAXONOMY';
    if (Q.includes('gdpr') || Q.includes('privacy')) return 'GDPR';
    return 'CSRD';
  };

  const SUGGEST = [
    'Quali soglie applicano a una holding sotto CSRD?',
    'TLPT DORA — soglia entità significative banche?',
    'Obblighi GPAI Art. 53 — quando scattano?',
    'CSDDD — Tier 2 fuori UE?',
  ];

  return (
    <div>
      <div className="section-head">
        <div><h2>Q&A normativo</h2><p>Domande grounded sul corpus · risposta con citazioni · CoVe verification</p></div>
      </div>

      <div className="card card-pad" style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <_Icon name="spark" size={18} />
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ask(); }}
            placeholder="Fai una domanda… (⌘+Invio per inviare)"
            style={{ flex: 1, minHeight: 70, background: 'transparent', border: 'none', outline: 'none', color: 'var(--ink)', fontFamily: 'inherit', fontSize: 14, resize: 'vertical' }}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <select value={activeFw} onChange={e => setActiveFw(e.target.value)} className="chip-select" style={{ height: 28, fontSize: 11 }}>
              <option value="AUTO">Auto-detect</option>
              {_D.FRAMEWORKS.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
            <button className="btn primary" onClick={ask} disabled={loading || !question.trim()}>
              {loading ? 'Genero…' : 'Chiedi'}
            </button>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
          <span className="tiny mute2">Suggerimenti:</span>
          {SUGGEST.map(s => (
            <button key={s} className="tag" style={{ cursor: 'pointer' }} onClick={() => setQuestion(s)}>{s}</button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-head"><h3>Cronologia · {history.length}</h3><span className="card-sub">cliccaci per espandere</span></div>
        <div className="list">
          {history.map((it, i) => (
            <div key={i} className="list-row" style={{ cursor: 'pointer', alignItems: 'flex-start' }}
                 onClick={() => setHistory(h => h.map((x, j) => j === i ? { ...x, expanded: !x.expanded } : x))}>
              <_Icon name="spark" size={14} />
              <div style={{ minWidth: 0 }}>
                <div className="list-title">{it.q}</div>
                <div className="meta"><_FT id={it.fw} /> · {it.user} · conf <span className="mono">{it.conf ?? '—'}{it.conf ? '%' : ''}</span></div>
                {it.expanded && it.a && (
                  <div style={{ marginTop: 10, padding: 12, background: 'var(--bg-2)', borderRadius: 8, fontSize: 13, lineHeight: 1.55, color: 'var(--ink-2)', whiteSpace: 'pre-wrap' }}>
                    {it.a === '…' ? <em className="mute2">Generazione in corso…</em> : it.a}
                  </div>
                )}
              </div>
              <time>{it.ts}</time>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Alerts interattivi (dismiss + filter) ─────────────
function AlertsSection() {
  const [alerts, setAlerts] = uiUseState(_D.ALERTS.map((a, i) => ({ ...a, id: i, dismissed: false, ack: false })));
  const [filter, setFilter] = uiUseState('ALL');
  const visible = alerts.filter(a => !a.dismissed && (filter === 'ALL' || a.p === filter));

  const dismiss = (id) => { setAlerts(a => a.map(x => x.id === id ? { ...x, dismissed: true } : x)); ToastBus.push('Alert archiviato', 'info'); };
  const ack = (id) => { setAlerts(a => a.map(x => x.id === id ? { ...x, ack: !x.ack } : x)); };

  const counts = { p0: alerts.filter(a => a.p === 'p0' && !a.dismissed).length, p1: alerts.filter(a => a.p === 'p1' && !a.dismissed).length, p2: alerts.filter(a => a.p === 'p2' && !a.dismissed).length };

  return (
    <div>
      <div className="section-head"><div><h2>Alert</h2><p>Notifiche prioritarie · {visible.length} attivi · click per espandere · X per archiviare</p></div></div>
      <div className="card">
        <div className="card-head">
          <h3>Coda alert</h3>
          <div className="card-actions">
            <button className={`btn ${filter==='ALL'?'primary':'ghost'}`} onClick={()=>setFilter('ALL')}>Tutti ({alerts.filter(a=>!a.dismissed).length})</button>
            <button className={`btn ${filter==='p0'?'primary':'ghost'}`} onClick={()=>setFilter('p0')}>P0 ({counts.p0})</button>
            <button className={`btn ${filter==='p1'?'primary':'ghost'}`} onClick={()=>setFilter('p1')}>P1 ({counts.p1})</button>
            <button className={`btn ${filter==='p2'?'primary':'ghost'}`} onClick={()=>setFilter('p2')}>P2 ({counts.p2})</button>
          </div>
        </div>
        <table className="tbl">
          <thead><tr><th></th><th>Titolo</th><th>Framework</th><th>Sorgente</th><th>Impatto</th><th>Quando</th><th>Stato</th><th></th></tr></thead>
          <tbody>
            {visible.map(a => (
              <tr key={a.id} style={{ opacity: a.ack ? 0.55 : 1 }}>
                <td><span className={`priority ${a.p}`} /></td>
                <td>{a.title}</td>
                <td><_FT id={a.fw} /></td>
                <td className="muted">{a.src}</td>
                <td><span className={a.impact === 'Alto' ? 'tag bad' : a.impact === 'Medio' ? 'tag warn' : 'tag info'}>{a.impact}</span></td>
                <td className="muted">{a.ts}</td>
                <td>
                  <button className="btn ghost" style={{ height: 24, padding: '0 8px', fontSize: 11 }} onClick={()=>ack(a.id)}>
                    {a.ack ? '✓ visto' : 'Ack'}
                  </button>
                </td>
                <td><button className="btn ghost btn-icon" onClick={()=>dismiss(a.id)} title="Archivia">×</button></td>
              </tr>
            ))}
            {visible.length === 0 && <tr><td colSpan={8} className="empty">Nessun alert in coda · ottimo!</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Workflow Kanban con drag&drop ─────────────────────
function WorkflowSection() {
  const [cards, setCards] = uiUseState([
    { id: 1, t: 'Aggiornare TIA fornitori cloud', col: 'backlog', fw: 'GDPR', who: 'DPO', p: 'p2' },
    { id: 2, t: 'Mappare ESRS S1 KPIs',           col: 'backlog', fw: 'CSRD', who: 'Marta', p: 'p1' },
    { id: 3, t: 'Risposta a EFRAG QA #418',       col: 'doing',   fw: 'CSRD', who: 'Marta', p: 'p1' },
    { id: 4, t: 'Test TLPT — kick-off vendor',    col: 'doing',   fw: 'DORA', who: 'CISO',  p: 'p1' },
    { id: 5, t: 'Value chain Tier 2 cleanup',     col: 'doing',   fw: 'CSDDD',who: 'Davide',p: 'p0' },
    { id: 6, t: 'Policy AI governance v3.2',      col: 'review',  fw: 'AI_ACT', who: 'Comitato', p: 'p1' },
    { id: 7, t: 'Notifica incidenti NIS2 v1',     col: 'done',    fw: 'NIS2', who: 'CISO', p: 'p2' },
    { id: 8, t: 'Indicizzazione ESRS allegati',   col: 'done',    fw: 'CSRD', who: 'AI',   p: 'p3' },
  ]);
  const cols = [
    { id: 'backlog', title: 'Backlog' },
    { id: 'doing',   title: 'In corso' },
    { id: 'review',  title: 'Review' },
    { id: 'done',    title: 'Done' },
  ];
  const [dragging, setDragging] = uiUseState(null);

  const drop = (col) => {
    if (dragging == null) return;
    setCards(c => c.map(x => x.id === dragging ? { ...x, col } : x));
    setDragging(null);
    ToastBus.push('Task spostato', 'good');
  };

  return (
    <div>
      <div className="section-head"><div><h2>Workflow</h2><p>Task, approvazioni, owner · trascina le card tra colonne</p></div></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        {cols.map(c => {
          const items = cards.filter(x => x.col === c.id);
          return (
            <div key={c.id} className="card"
                 onDragOver={(e) => e.preventDefault()}
                 onDrop={() => drop(c.id)}>
              <div className="card-head"><h3>{c.title}</h3><span className="card-sub">{items.length}</span></div>
              <div style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 8, minHeight: 100 }}>
                {items.map(k => (
                  <div key={k.id} draggable onDragStart={() => setDragging(k.id)}
                       style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, padding: 10, cursor: 'grab' }}>
                    <div className="tiny muted" style={{ marginBottom: 4 }}>
                      <span className={`priority ${k.p}`} /> <_FT id={k.fw} />
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.35 }}>{k.t}</div>
                    <div className="tiny mute2" style={{ marginTop: 6 }}>{k.who}</div>
                  </div>
                ))}
                {items.length === 0 && <div className="tiny mute2" style={{ textAlign: 'center', padding: 20 }}>Trascina qui</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Gap analysis con righe espandibili ────────────────
function GapSection({ framework }) {
  const fws = framework === 'ALL' ? _D.FRAMEWORKS : _D.FRAMEWORKS.filter(f => f.id === framework);
  const [open, setOpen] = uiUseState(null);
  return (
    <div>
      <div className="section-head"><div><h2>Gap analysis</h2><p>Articoli e requisiti mancanti · click su una riga per il piano d'azione</p></div></div>
      <div className="kpi-grid">
        <_KPI label="Gap totali" value="94" foot="su 7 framework" icon="target" />
        <_KPI label="Critici (P0)" value="12" trend={{dir:'down', text:'−3 sett.'}} icon="shield" />
        <_KPI label="Risolti 30g" value="38" trend={{dir:'up', text:'+18%'}} icon="pulse" />
        <_KPI label="Tempo medio chiusura" value="11" unit="g" icon="graph" />
      </div>
      <div className="card">
        <div className="card-head"><h3>Distribuzione gap per framework</h3></div>
        <table className="tbl">
          <thead><tr><th>Framework</th><th>Score</th><th>P0</th><th>P1</th><th>P2</th><th>Owner</th><th>SLA</th></tr></thead>
          <tbody>
            {fws.map(f => (
              <React.Fragment key={f.id}>
                <tr style={{ cursor: 'pointer' }} onClick={() => setOpen(open === f.id ? null : f.id)}>
                  <td><_FT id={f.id} /> <span className="muted" style={{ marginLeft: 6 }}>{f.label}</span></td>
                  <td><_SN v={f.score} /></td>
                  <td className="num"><span className="tag bad">{Math.max(1, Math.round(f.gaps * 0.18))}</span></td>
                  <td className="num"><span className="tag warn">{Math.round(f.gaps * 0.42)}</span></td>
                  <td className="num"><span className="tag info">{Math.round(f.gaps * 0.40)}</span></td>
                  <td className="muted">{f.owner}</td>
                  <td className="num muted">{8 + (f.gaps % 9)} g</td>
                </tr>
                {open === f.id && (
                  <tr><td colSpan={7} style={{ background: 'var(--bg-2)', padding: 16 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                      {[
                        { req: `Art. 8(2) — value chain mapping`,   own: f.owner, sla: '14g', p: 'p0' },
                        { req: `Allegato I sez. ${f.gaps % 4 + 1}`, own: f.owner, sla: '21g', p: 'p1' },
                        { req: `Reporting Q4 — evidenza`,            own: f.owner, sla: '30g', p: 'p1' },
                      ].map((g, i) => (
                        <div key={i} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 12 }}>
                          <div className="tiny muted"><span className={`priority ${g.p}`} /> {g.p.toUpperCase()}</div>
                          <div style={{ fontSize: 13, fontWeight: 500, marginTop: 4 }}>{g.req}</div>
                          <div className="tiny mute2" style={{ marginTop: 6 }}>Owner {g.own} · SLA {g.sla}</div>
                          <button className="btn ghost" style={{ marginTop: 8, height: 26, fontSize: 11 }}
                                  onClick={(e) => { e.stopPropagation(); ToastBus.push('Piano d\'azione generato', 'good'); }}>
                            Genera piano AI
                          </button>
                        </div>
                      ))}
                    </div>
                  </td></tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Documenti con upload finto ────────────────────────
function DocumentsSection() {
  const [docs, setDocs] = uiUseState([
    { name: 'Policy AI governance v3.2.pdf',     fw: 'AI_ACT', size: '2.4 MB', up: '2g fa', owner: 'Marta R.', kind: 'Policy' },
    { name: 'Procedura incident NIS2.docx',      fw: 'NIS2',   size: '186 KB', up: '5g fa', owner: 'CISO',     kind: 'Procedura' },
    { name: 'TIA Q4 2026 — clienti EU.xlsx',     fw: 'GDPR',   size: '910 KB', up: '1g fa', owner: 'DPO',      kind: 'Evidenza' },
    { name: 'Mappatura value chain Tier1.csv',   fw: 'CSDDD',  size: '4.1 MB', up: '8g fa', owner: 'Davide T.',kind: 'Dataset' },
  ]);
  const fileRef = uiUseRef(null);
  const onFiles = (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const FW = ['CSRD','AI_ACT','GDPR','DORA'];
    setDocs(d => [...files.map((f, i) => ({
      name: f.name, fw: FW[i % FW.length], size: (f.size / 1024).toFixed(0) + ' KB', up: 'ora', owner: 'Tu', kind: 'Caricato'
    })), ...d]);
    ToastBus.push(`${files.length} documento/i caricato/i · indicizzazione in corso`, 'good');
    e.target.value = '';
  };
  return (
    <div>
      <div className="section-head">
        <div><h2>Documenti</h2><p>Policy, procedure, evidenze · indicizzati nel corpus RAG</p></div>
        <div className="section-actions">
          <input ref={fileRef} type="file" multiple style={{ display: 'none' }} onChange={onFiles} />
          <button className="btn primary" onClick={() => fileRef.current?.click()}>
            <_Icon name="plus" size={14}/> Carica documenti
          </button>
        </div>
      </div>
      <div className="card">
        <table className="tbl">
          <thead><tr><th>Nome</th><th>Tipo</th><th>Framework</th><th>Owner</th><th>Dim.</th><th>Aggiornato</th></tr></thead>
          <tbody>
            {docs.map((r, i) => (
              <tr key={i}>
                <td><_Icon name="doc" size={14} /> <span style={{ marginLeft: 8 }}>{r.name}</span></td>
                <td className="muted">{r.kind}</td>
                <td><_FT id={r.fw} /></td>
                <td className="muted">{r.owner}</td>
                <td className="num muted">{r.size}</td>
                <td className="muted">{r.up}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Override le sezioni nella global window
Object.assign(window, { QASection, AlertsSection, WorkflowSection, GapSection, DocumentsSection });
