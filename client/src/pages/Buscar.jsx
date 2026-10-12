import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { Empty, PageHeader } from "../components/ui.jsx";
import { dayOffset, fmtDuration, fmtRelative, fmtTime } from "../format.js";
import { useCopilotRefresh, useCopilotView } from "../copilot-view.js";

const MODES = [
  { value: "both", label: "Texto y aspecto" },
  { value: "text", label: "Solo texto (OCR)" },
  { value: "visual", label: "Solo aspecto" },
];

// snippet() marks matches with [ ] — render them as <mark> without trusting HTML.
function Snippet({ text }) {
  if (!text) return null;
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

// Which side found the moment: the words on it (texto) and/or how it looked (aspecto, with the cosine of the best frame).
function Via({ hit }) {
  const via = hit.via || [];
  if (!via.length) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {via.includes("text") && <span className="chip" title="Coincide con el texto reconocido, el título o la aplicación">texto</span>}
      {via.includes("visual") && (
        <span className="chip" title="Se parece a lo que describes (similitud del coseno de la mejor pantalla)">
          aspecto{hit.visual_score != null ? ` ${Number(hit.visual_score).toFixed(2)}` : ""}
        </span>
      )}
    </div>
  );
}

// The API already collapses runs of identical frames into moments; each row is one moment.
function Moment({ hit, openFrame, onSimilar }) {
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
          <Via hit={hit} />
        </div>
      </button>
      <div className="mt-2 flex flex-wrap items-center gap-1 px-1">
        {hit.count > 1 && strip.map((id) => (
          <button key={id} type="button" onClick={() => openFrame(id)} aria-label={`Abrir captura ${id}`} className="rounded border" style={{ borderColor: id === hit.id ? "var(--accent)" : "var(--line)" }}>
            <img src={api.thumbUrl(id)} alt="" loading="lazy" className="h-10 w-[72px] rounded object-cover" />
          </button>
        ))}
        {hit.count > 1 && hit.frame_ids.length > 6 && (
          <button type="button" className="btn-link ml-1 text-[12px]" onClick={() => setAll((v) => !v)}>{all ? "Menos" : `Ver las ${hit.frame_ids.length}`}</button>
        )}
        {onSimilar && <button type="button" className="btn-link ml-auto text-[12px]" onClick={() => onSimilar(hit.id)}>Ver pantallas parecidas</button>}
      </div>
    </li>
  );
}

export default function Buscar() {
  const { openFrame, status, pendingSimilar, takeSimilar } = useApp();
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("both");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [app, setApp] = useState("");
  const [apps, setApps] = useState([]);
  const [result, setResult] = useState(null);
  const [similarTo, setSimilarTo] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [ran, setRan] = useState(null); // the parameters of the search whose results are on screen

  const visual = status?.visual;
  const visualActive = Boolean(visual?.active);

  useEffect(() => { api.apps({}).then((a) => setApps(a.apps)).catch(() => {}); }, []);

  const search = async (event) => {
    event?.preventDefault();
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    setSimilarTo(null);
    try {
      const params = { q: q.trim(), from, to, app, mode };
      const found = await api.search({ ...params, limit: 60 });
      setResult(found);
      setRan({ ...params, moments_total: found.moments_total });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const findSimilar = useCallback(async (id) => {
    setLoading(true);
    setError(null);
    try {
      const found = await api.similar(id, { from, to, app, limit: 40 });
      setResult(found);
      setSimilarTo(id);
      setRan({ from, to, app, similar_to: id, moments_total: found.moments_total });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [from, to, app]);

  useEffect(() => {
    if (pendingSimilar) {
      const id = takeSimilar();
      if (id) findSimilar(id);
    }
  }, [pendingSimilar, takeSimilar, findSimilar]);

  // The assistant finished a turn: run the same search again (the form fields the user is typing are left alone).
  useCopilotRefresh(async () => {
    if (!ran) return;
    try {
      const found = ran.similar_to
        ? await api.similar(ran.similar_to, { from: ran.from, to: ran.to, app: ran.app, limit: 40 })
        : await api.search({ q: ran.q, from: ran.from, to: ran.to, app: ran.app, mode: ran.mode, limit: 60 });
      setResult(found);
      setRan((current) => current && { ...current, moments_total: found.moments_total });
    } catch { /* the old results stay */ }
  });
  const draftNow = { q: q.trim(), mode, from, to, app };
  const unsaved = ran && !ran.similar_to ? JSON.stringify(draftNow) !== JSON.stringify({ q: ran.q, mode: ran.mode, from: ran.from, to: ran.to, app: ran.app }) : Boolean(q.trim() || from || to || app);
  useCopilotView("search", {
    ran,
    hits: result ? result.hits.slice(0, 5).map((h) => ({ id: h.id, window_title: h.window_title, app: h.app, first_at: h.first_at })) : [],
    draft: unsaved ? draftNow : null,
  });

  const preset = (days) => { setFrom(dayOffset(-days)); setTo(""); };
  const visualNote = result && result.mode !== "similar" && mode !== "text" && result.visual && !result.visual.used ? result.visual.reason : null;

  return (
    <div>
      <PageHeader title="Buscar" description="Busca en el texto reconocido, los títulos de ventana y los nombres de aplicación (todas las palabras deben aparecer; la última vale como prefijo), o describe cómo se veía la pantalla: «la gráfica azul», «código en fondo oscuro». Las pantallas repetidas de un mismo momento se agrupan." />
      <form onSubmit={search} className="panel mb-5">
        <div className="grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1.2fr)_repeat(3,minmax(0,1fr))_auto]">
          <label className="block">
            <span className="label">Texto o descripción</span>
            <input className="field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="un error, una frase… o «la pantalla con la gráfica azul»" autoFocus />
          </label>
          <label className="block">
            <span className="label">Buscar por</span>
            <select className="field" value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Cómo buscar">
              {MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
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
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button type="button" className="btn btn-sm" onClick={() => preset(0)}>Hoy</button>
          <button type="button" className="btn btn-sm" onClick={() => { setFrom(dayOffset(-1)); setTo(dayOffset(-1)); }}>Ayer</button>
          <button type="button" className="btn btn-sm" onClick={() => preset(7)}>Últimos 7 días</button>
          <button type="button" className="btn btn-sm" onClick={() => { setFrom(""); setTo(""); }}>Sin fecha</button>
          {visual && (
            <span className="help ml-auto" data-testid="visual-state">
              {visualActive
                ? `Búsqueda por aspecto: ${visual.indexed} de ${visual.total} pantallas indexadas${visual.pending ? ` (${visual.pending} pendientes)` : ""}`
                : visual.enabled ? "Búsqueda por aspecto: falta descargar el modelo (Ajustes)" : "Búsqueda por aspecto desactivada (Ajustes)"}
            </span>
          )}
        </div>
      </form>

      {error && <p className="mb-4" style={{ color: "var(--danger-ink)" }}>{error}</p>}
      {visualNote && <p className="help mb-3">Solo se ha buscado por texto. {visualNote}</p>}
      {result && result.hits.length === 0 && <Empty title="Nada por aquí">{result.mode === "similar" ? "No hay otras pantallas parecidas en ese rango." : "Prueba con menos palabras, otra descripción o amplía las fechas. El OCR puede haber leído mal alguna letra."}</Empty>}
      {result && result.hits.length > 0 && (
        <div>
          <p className="help mb-3" data-testid="result-summary">
            {result.mode === "similar"
              ? `${result.moments_total} momentos parecidos a la captura ${similarTo ?? result.frame_id}, el más parecido primero`
              : `${result.moments_total} momentos (${result.frames_total} pantallas) para «${result.query}», la mejor coincidencia primero${result.mode === "visual" ? " (por aspecto)" : result.mode === "both" && result.visual?.used ? " (texto y aspecto)" : ""}`}
            {result.moments_total > result.hits.length ? `; se muestran ${result.hits.length}` : ""}.
          </p>
          <ul className="grid gap-2">
            {result.hits.map((hit) => <Moment key={hit.id} hit={hit} openFrame={openFrame} onSimilar={visualActive ? findSimilar : null} />)}
          </ul>
        </div>
      )}
    </div>
  );
}
