import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { Empty, PageHeader } from "../components/ui.jsx";
import { dayOffset, fmtDuration, fmtRelative, fmtTime } from "../format.js";

// snippet() marks matches with [ ] — render them as <mark> without trusting HTML.
function Snippet({ text }) {
  const parts = text.split(/(\[[^\]]+\])/g);
  return (
    <p className="text-[13px] leading-snug">
      {parts.map((part, i) => (part.startsWith("[") && part.endsWith("]") ? <mark key={i}>{part.slice(1, -1)}</mark> : <React.Fragment key={i}>{part}</React.Fragment>))}
    </p>
  );
}

// "hoy 17:32" for a single frame, "hoy 17:32–17:41" for a moment that spans several.
function momentTime(hit) {
  const first = fmtRelative(hit.first_at);
  if (hit.count <= 1) return first;
  return `${first}–${fmtTime(hit.last_at).slice(0, 5)}`;
}

// The API already collapses runs of identical frames into moments; each row is one moment.
function Moment({ hit, openFrame }) {
  const [all, setAll] = useState(false);
  const strip = all ? hit.frame_ids : hit.frame_ids.slice(0, 6);
  return (
    <li className="rounded-lg border p-2" style={{ borderColor: "var(--line)", background: "var(--white)" }}>
      <button type="button" className="frame-card grid grid-cols-[112px_minmax(0,1fr)] gap-3 md:grid-cols-[160px_minmax(0,1fr)]" onClick={() => openFrame(hit.id)}>
        <img className="thumb" src={api.thumbUrl(hit.id)} alt="" loading="lazy" />
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="truncate text-[13px] font-semibold">{hit.window_title || "(sin título)"}</span>
            <span className="help">{hit.app || "app desconocida"}</span>
          </div>
          <div className="help num">
            {momentTime(hit)} · {hit.count === 1 ? "1 pantalla" : `${hit.count} pantallas`} · {fmtDuration(hit.duration_s)} en pantalla
          </div>
          <Snippet text={hit.snippet} />
        </div>
      </button>
      {hit.count > 1 && (
        <div className="mt-2 flex flex-wrap items-center gap-1 px-1">
          {strip.map((id) => (
            <button key={id} type="button" onClick={() => openFrame(id)} aria-label={`Abrir captura ${id}`} className="rounded border" style={{ borderColor: id === hit.id ? "var(--accent)" : "var(--line)" }}>
              <img src={api.thumbUrl(id)} alt="" loading="lazy" className="h-10 w-[72px] rounded object-cover" />
            </button>
          ))}
          {hit.frame_ids.length > 6 && (
            <button type="button" className="btn-link ml-1 text-[12px]" onClick={() => setAll((v) => !v)}>{all ? "Menos" : `Ver las ${hit.frame_ids.length}`}</button>
          )}
        </div>
      )}
    </li>
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
      setResult(await api.search({ q: q.trim(), from, to, app, limit: 60 }));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const preset = (days) => { setFrom(dayOffset(-days)); setTo(""); };

  return (
    <div>
      <PageHeader title="Buscar" description="Busca en el texto reconocido, los títulos de ventana y los nombres de aplicación. Todas las palabras deben aparecer; la última vale como prefijo. Las pantallas repetidas de un mismo momento se agrupan." />
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
          <p className="help mb-3">
            {result.moments_total} momentos ({result.frames_total} pantallas) para «{result.query}», la mejor coincidencia primero
            {result.moments_total > result.hits.length ? `; se muestran ${result.hits.length}` : ""}.
          </p>
          <ul className="grid gap-2">
            {result.hits.map((hit) => <Moment key={hit.id} hit={hit} openFrame={openFrame} />)}
          </ul>
        </div>
      )}
    </div>
  );
}
