// components.jsx — small visual primitives shared between sections

const Icon = window.NormaIcon;

function KPI({ label, value, unit, trend, foot, tint, icon }) {
  return (
    <div className="kpi" style={{ '--kpi-tint': tint || 'transparent' }}>
      <div className="kpi-label">
        {icon && <Icon name={icon} size={12} />} {label}
      </div>
      <div className="kpi-value">
        {value}{unit && <span className="kpi-unit">{unit}</span>}
      </div>
      {trend && (
        <div className={`kpi-trend ${trend.dir}`}>
          {trend.dir === 'up' ? '▲' : trend.dir === 'down' ? '▼' : '–'} {trend.text}
        </div>
      )}
      {foot && <div className="kpi-foot">{foot}</div>}
    </div>
  );
}

function Sparkline({ data, color = 'var(--accent)', height = 36 }) {
  const w = 200, h = height;
  const max = Math.max(...data), min = Math.min(...data);
  const span = max - min || 1;
  const step = w / (data.length - 1);
  const pts = data.map((v, i) => `${(i * step).toFixed(1)},${(h - ((v - min) / span) * (h - 4) - 2).toFixed(1)}`).join(' ');
  const area = `0,${h} ${pts} ${w},${h}`;
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="sg" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={area} fill="url(#sg)" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function AreaChart({ data, color = 'var(--accent)', height = 200, labels }) {
  const w = 720, h = height;
  const pad = { l: 30, r: 10, t: 10, b: 22 };
  const cw = w - pad.l - pad.r, ch = h - pad.t - pad.b;
  const max = Math.max(...data), min = 0;
  const span = max - min || 1;
  const step = cw / (data.length - 1);
  const pts = data.map((v, i) => [pad.l + i * step, pad.t + ch - ((v - min) / span) * ch]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const area = `${line} L ${pad.l + cw} ${pad.t + ch} L ${pad.l} ${pad.t + ch} Z`;
  const gridY = [0, 0.25, 0.5, 0.75, 1].map(t => pad.t + ch * t);
  return (
    <svg className="area-chart" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="ag" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {gridY.map((y, i) => (
        <line key={i} x1={pad.l} x2={w - pad.r} y1={y} y2={y} stroke="rgba(255,255,255,0.05)" />
      ))}
      {[0, 0.5, 1].map((t, i) => (
        <text key={i} x={pad.l - 6} y={pad.t + ch * (1 - t) + 3} textAnchor="end"
              fontSize="9" fill="var(--ink-4)" fontFamily="Geist Mono">
          {Math.round(min + span * t)}
        </text>
      ))}
      <path d={area} fill="url(#ag)" />
      <path d={line} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
      {labels && labels.map((lab, i) => (
        i % Math.ceil(labels.length / 6) === 0 ? (
          <text key={i} x={pad.l + i * step} y={h - 6} textAnchor="middle"
                fontSize="9" fill="var(--ink-4)">{lab}</text>
        ) : null
      ))}
    </svg>
  );
}

function ScoreBar({ value, color }) {
  return (
    <div className="score-bar" style={{ '--fw-color': color }}>
      <span style={{ '--w': `${value}%` }} />
    </div>
  );
}

function FwTag({ id }) {
  const fw = (window.NormaData.FRAMEWORKS.find(f => f.id === id)) || { name: id, color: 'var(--accent)' };
  return <span className="tag fw" style={{ '--fw-color': fw.color }}>{fw.name}</span>;
}

function ScoreNum({ v }) {
  const cls = v >= 80 ? 'good' : v >= 60 ? 'warn' : 'bad';
  return <span className={`score-num ${cls}`}>{v}<span style={{ fontSize: 11, color: 'var(--ink-4)' }}>/100</span></span>;
}

window.NormaUI = { KPI, Sparkline, AreaChart, ScoreBar, FwTag, ScoreNum };
