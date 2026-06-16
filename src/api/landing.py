"""Landing page HTML and route.

Extracted from main.py to reduce its size.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NormaAI — EU Regulatory Intelligence</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#06080f;--surface:#0d1117;--surface2:#161b22;--border:rgba(99,102,241,.12);--border-h:rgba(99,102,241,.3);--text:#e2e8f0;--text2:#94a3b8;--text3:#64748b;--accent:#818cf8;--accent2:#6366f1;--green:#22c55e;--yellow:#fbbf24;--red:#ef4444;--radius:12px;--font:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,sans-serif;--mono:'SF Mono',Monaco,'Cascadia Code',monospace}
body{font-family:var(--font);background:var(--bg);color:var(--text);min-height:100vh;line-height:1.5}
.wrap{max-width:1120px;margin:0 auto;padding:0 28px}

/* Header */
.hdr{padding:40px 0 28px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:14px}
.logo-icon{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,#6366f1,#4f46e5);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:800;color:#fff;letter-spacing:-1px}
.logo-text{font-size:26px;font-weight:700;letter-spacing:-.5px}
.logo-text em{font-style:normal;font-weight:300;color:var(--text2)}
.ver{font-size:11px;padding:3px 10px;border-radius:20px;background:rgba(99,102,241,.12);color:var(--accent);font-weight:600;margin-left:8px}
.hdr-links{display:flex;gap:8px}
.hdr-links a{padding:8px 18px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:500;transition:.2s}
.btn-p{background:linear-gradient(135deg,#6366f1,#4f46e5);color:#fff}
.btn-p:hover{opacity:.9;transform:translateY(-1px)}
.btn-s{background:var(--surface2);color:var(--text2);border:1px solid var(--border)}
.btn-s:hover{border-color:var(--border-h);color:var(--text)}

/* Status bar */
.status-bar{display:flex;align-items:center;gap:20px;padding:16px 0;margin-top:4px;font-size:13px;color:var(--text3);flex-wrap:wrap}
.status-bar .dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}
.dot-g{background:var(--green);box-shadow:0 0 6px rgba(34,197,94,.5)}
.dot-y{background:var(--yellow);box-shadow:0 0 6px rgba(251,191,36,.4)}
.dot-r{background:var(--red);box-shadow:0 0 6px rgba(239,68,68,.4)}
.status-bar span{display:flex;align-items:center}

/* Grid */
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:28px 0}
@media(max-width:768px){.grid{grid-template-columns:1fr}}

/* Cards */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;transition:border-color .2s}
.card:hover{border-color:var(--border-h)}
.card-title{font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:var(--text3);margin-bottom:16px;font-weight:600}
.card-full{grid-column:1/-1}

/* Stat row */
.stat-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
@media(max-width:640px){.stat-row{grid-template-columns:repeat(2,1fr)}}
.stat{text-align:center;padding:18px 12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius)}
.stat-n{font-size:32px;font-weight:700;color:var(--accent);line-height:1.1}
.stat-l{font-size:12px;color:var(--text3);margin-top:4px}

/* Framework badges */
.fw-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px}
.fw{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:8px;background:var(--surface2);border:1px solid transparent;transition:.2s;cursor:default}
.fw:hover{border-color:var(--border-h)}
.fw-dot{width:7px;height:7px;border-radius:50%;background:var(--green);flex-shrink:0}
.fw b{font-size:13px;font-weight:600}
.fw small{font-size:11px;color:var(--text3);margin-left:auto;white-space:nowrap}

/* Endpoints */
.ep-list{display:flex;flex-direction:column;gap:4px}
.ep{display:flex;align-items:center;gap:12px;padding:11px 14px;border-radius:8px;transition:.15s;cursor:pointer;text-decoration:none;color:inherit}
.ep:hover{background:var(--surface2)}
.badge{font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;min-width:48px;text-align:center;letter-spacing:.3px;font-family:var(--mono)}
.badge-post{background:rgba(34,197,94,.12);color:#4ade80}
.badge-get{background:rgba(59,130,246,.12);color:#60a5fa}
.ep-path{font-family:var(--mono);font-size:13px;color:var(--text)}
.ep-desc{font-size:12px;color:var(--text3);margin-left:auto}

/* Engine badges */
.engines{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.eng{display:flex;align-items:center;gap:6px;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:500}
.eng-on{background:rgba(34,197,94,.1);color:#4ade80;border:1px solid rgba(34,197,94,.2)}
.eng-off{background:rgba(100,116,139,.08);color:var(--text3);border:1px solid var(--border)}

/* Architecture */
.arch{font-family:var(--mono);font-size:12px;color:var(--text2);line-height:1.7;padding:16px;background:var(--surface2);border-radius:8px;overflow-x:auto;white-space:pre}

/* Footer */
.ftr{padding:24px 0;text-align:center;color:var(--text3);font-size:12px;border-top:1px solid var(--border);margin-top:12px}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <div class="brand">
      <div class="logo-icon">N</div>
      <div><span class="logo-text">NormaAI <em>Intelligence</em></span><span class="ver">v0.3.0</span></div>
    </div>
    <div class="hdr-links">
      <a href="/docs" class="btn-p">API Docs</a>
      <a href="/redoc" class="btn-s">ReDoc</a>
    </div>
  </div>

  <div class="status-bar" id="status-bar">
    <span><span class="dot dot-g" id="dot-sys"></span> <span id="sys-status">Loading...</span></span>
    <span id="llm-info"></span>
    <span id="db-info"></span>
  </div>

  <div class="stat-row" style="margin-top:20px">
    <div class="stat"><div class="stat-n" id="s-chunks">&mdash;</div><div class="stat-l">Chunks Indexed</div></div>
    <div class="stat"><div class="stat-n">7</div><div class="stat-l">EU Frameworks</div></div>
    <div class="stat"><div class="stat-n">9</div><div class="stat-l">Core Regulations</div></div>
    <div class="stat"><div class="stat-n" id="s-uptime">&mdash;</div><div class="stat-l">System Status</div></div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">Active Frameworks</div>
      <div class="fw-grid">
        <div class="fw"><span class="fw-dot"></span><b>CSRD</b><small>Sustainability</small></div>
        <div class="fw"><span class="fw-dot"></span><b>CSDDD</b><small>Due Diligence</small></div>
        <div class="fw"><span class="fw-dot"></span><b>AI Act</b><small>AI Regulation</small></div>
        <div class="fw"><span class="fw-dot"></span><b>DORA</b><small>Digital Ops</small></div>
        <div class="fw"><span class="fw-dot"></span><b>NIS2</b><small>Cybersecurity</small></div>
        <div class="fw"><span class="fw-dot"></span><b>Taxonomy</b><small>Green Finance</small></div>
        <div class="fw"><span class="fw-dot"></span><b>GDPR</b><small>Data Privacy</small></div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Intelligence Endpoints</div>
      <div class="ep-list">
        <a class="ep" href="/docs#/Intelligence/ask_question_api_v1_qa_post">
          <span class="badge badge-post">POST</span>
          <span class="ep-path">/api/v1/qa</span>
          <span class="ep-desc">Regulatory Q&amp;A</span>
        </a>
        <a class="ep" href="/docs#/Intelligence/run_gap_analysis_endpoint_api_v1_gap_analysis_post">
          <span class="badge badge-post">POST</span>
          <span class="ep-path">/api/v1/gap-analysis</span>
          <span class="ep-desc">Gap Analysis</span>
        </a>
        <a class="ep" href="/docs#/Intelligence/monitor_change_api_v1_monitor_post">
          <span class="badge badge-post">POST</span>
          <span class="ep-path">/api/v1/monitor</span>
          <span class="ep-desc">Change Impact</span>
        </a>
        <a class="ep" href="/docs#/Data/trigger_crawl_api_v1_crawl_post">
          <span class="badge badge-post">POST</span>
          <span class="ep-path">/api/v1/crawl</span>
          <span class="ep-desc">EUR-Lex Crawl</span>
        </a>
        <a class="ep" href="/api/v1/stats">
          <span class="badge badge-get">GET</span>
          <span class="ep-path">/api/v1/stats</span>
          <span class="ep-desc">Health &amp; Stats</span>
        </a>
        <a class="ep" href="/api/v1/processors">
          <span class="badge badge-get">GET</span>
          <span class="ep-path">/api/v1/processors</span>
          <span class="ep-desc">OCR Engines</span>
        </a>
      </div>
    </div>

    <div class="card card-full">
      <div class="card-title">Document Processing Engines</div>
      <div style="display:flex;gap:24px;flex-wrap:wrap">
        <div style="flex:1;min-width:280px">
          <div style="font-size:14px;font-weight:600;margin-bottom:8px;color:var(--text)">Dual-Engine Architecture</div>
          <div style="font-size:13px;color:var(--text2);margin-bottom:12px">
            NormaAI routes documents to the optimal processor based on type and quality.
            dots.ocr handles complex visual documents; Docling handles clean digital files.
          </div>
          <div class="engines" id="engines">
            <span class="eng eng-off" id="eng-dots"><span class="dot dot-r" style="width:6px;height:6px"></span>dots.ocr</span>
            <span class="eng eng-off" id="eng-docling"><span class="dot dot-r" style="width:6px;height:6px"></span>Docling</span>
            <span class="eng eng-on"><span class="dot dot-g" style="width:6px;height:6px"></span>BeautifulSoup</span>
          </div>
        </div>
        <div style="flex:1;min-width:280px">
          <div class="arch">Document ──┬── Scanned/Image ── dots.ocr ──┐
           │                             │
           ├── Clean PDF ───── Docling ───┤
           │                             │
           └── HTML ────── BS4 fallback ──┘
                                         │
                              Chunker ── Qdrant</div>
        </div>
      </div>
    </div>
  </div>

  <div class="ftr">NormaAI &copy; 2026 &mdash; Gemini AI + EUR-Lex SPARQL + Qdrant Hybrid Search + dots.ocr / Docling</div>
</div>

<script>
(async()=>{
  try{
    const [stats,procs]=await Promise.all([
      fetch('/api/v1/stats').then(r=>r.json()),
      fetch('/api/v1/processors').then(r=>r.json()).catch(()=>null)
    ]);
    const c=stats.qdrant?.points_count;
    if(c!==undefined)document.getElementById('s-chunks').textContent=Number(c).toLocaleString();
    const ok=stats.qdrant_available&&stats.llm_available;
    const partial=stats.qdrant_available&&!stats.llm_available;
    const dot=document.getElementById('dot-sys');
    const st=document.getElementById('s-uptime');
    const ss=document.getElementById('sys-status');
    if(ok){dot.className='dot dot-g';ss.textContent='All Systems Online';st.textContent='Online';st.style.color='#4ade80'}
    else if(partial){dot.className='dot dot-y';ss.textContent='Partial — LLM Unavailable';st.textContent='Partial';st.style.color='#fbbf24'}
    else{dot.className='dot dot-r';ss.textContent='Degraded';st.textContent='Down';st.style.color='#ef4444'}
    const li=document.getElementById('llm-info');
    if(stats.llm_provider)li.innerHTML='LLM: <b style="color:var(--text)">'+stats.llm_provider.toUpperCase()+' / '+stats.llm_model+'</b>';
    const di=document.getElementById('db-info');
    if(stats.qdrant_available)di.innerHTML='Qdrant: <b style="color:var(--green)">Connected</b>';
    else di.innerHTML='Qdrant: <b style="color:var(--red)">Offline</b>';
    if(procs){
      if(procs.dots_ocr?.available){
        const e=document.getElementById('eng-dots');
        e.className='eng eng-on';e.innerHTML='<span class="dot dot-g" style="width:6px;height:6px"></span>dots.ocr ('+procs.dots_ocr.mode+')';
      }
      if(procs.docling?.available){
        const e=document.getElementById('eng-docling');
        e.className='eng eng-on';e.innerHTML='<span class="dot dot-g" style="width:6px;height:6px"></span>Docling';
      }
    }
  }catch(e){
    document.getElementById('sys-status').textContent='Connection Error';
    document.getElementById('dot-sys').className='dot dot-r';
  }
})();
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def landing_page():
    """Serve the NormaAI landing page."""
    return HTMLResponse(content=LANDING_HTML)
