import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { Empty, PageHeader } from "../components/ui.jsx";
import { dayOffset, fmtDateTime, fmtDuration } from "../format.js";

// snippet() marks matches with [ ] — render them as <mark> without trusting HTML.
function Snippet({ text }) {
  const parts = text.split(/(\[[^\]]+\])/g);
  return (
    <p className="text-[13px] leading-snug">
      {parts.map((part, i) => (part.startsWith("[") && part.endsWith("]") ? <mark key={i}>{part.slice(1, -1)}</mark> : <React.Fragment key={i}>{part}</React.Fragment>))}
    </p>
  );
}

export default function Buscar() {
  const { openFrame } = useApp();
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [app, setApp] = useState("");
  const [apps, setApps] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.apps({}).then((a) => setApps(a.apps)).catch(() => {}); }, []);

  const search = async (event) => {
    event?.preventDefault();
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await api.search({ q: q.trim(), from, to, app, limit: 100 }));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const preset = (days) => { setFrom(dayOffset(-days)); setTo(""); };

  return (
    <div>
      <PageHeader title="Buscar" description="Busca en el texto reconocido, los títulos de ventana y los nombres de aplicación. Todas las palabras deben aparecer; la última vale como prefijo." />
      <form onSubmit={search} className="panel mb-5">
        <div className="grid gap-3 md:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))_auto]">
          <label className="block">
            <span className="label">Texto</span>
            <input className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="error que viste, una frase, un nombre…" autoFocus />
          </label>
          <label className="block">
            <span className="label">Desde</span>
            <input type="date" className="field" value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="block">
            <span className="label">Hasta</span>
            <input type="date" className="field" value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          <label className="block">
            <span className="label">Aplicación</span>
            <select className="field" value={app} onChange={(e) => setApp(e.target.value)}>
              <option value="">Todas</option>
              {apps.map((a) => <option key={a.app} value={a.app}>{a.app || "(desconocida)"}</option>)}
            </select>
          </label>
          <div className="flex items-end">
            <button type="submit" className="btn btn-primary w-full md:w-auto" disabled={loading || !q.trim()}>{loading ? "Buscando…" : "Buscar"}</button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="btn btn-sm" onClick={() => preset(0)}>Hoy</button>
          <button type="button" className="btn btn-sm" onClick={() => { setFrom(dayOffset(-1)); setTo(dayOffset(-1)); }}>Ayer</button>
          <button type="button" className="btn btn-sm" onClick={() => preset(7)}>Últimos 7 días</button>
          <button type="button" className="btn btn-sm" onClick={() => { setFrom(""); setTo(""); }}>Sin fecha</button>
        </div>
      </form>

      {error && <p className="mb-4" style={{ color: "var(--danger-ink)" }}>{error}</p>}
      {result && result.hits.length === 0 && <Empty title="Nada por aquí">Prueba con menos palabras o amplía las fechas. El OCR puede haber leído mal alguna letra.</Empty>}
      {result && result.hits.length > 0 && (
        <div>
          <p className="help mb-3">{result.hits.length} resultados para «{result.query}», ordenados por relevancia.</p>
          <ul className="grid gap-2">
            {result.hits.map((hit) => (
              <li key={hit.id}>
                <button type="button" className="frame-card grid grid-cols-[112px_minmax(0,1fr)] gap-3 md:grid-cols-[160px_minmax(0,1fr)]" onClick={() => openFrame(hit.id)}>
                  <img className="thumb" src={api.thumbUrl(hit.id)} alt="" loading="lazy" />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="truncate text-[13px] font-semibold">{hit.window_title || "(sin título)"}</span>
                      <span className="help">{hit.app || "app desconocida"}</span>
                    </div>
                    <div className="help num">{fmtDateTime(hit.captured_at)} · {fmtDuration(hit.duration_s)} en pantalla</div>
                    <Snippet text={hit.snippet} />
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
