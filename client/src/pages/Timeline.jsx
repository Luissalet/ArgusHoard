import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { Empty, PageHeader } from "../components/ui.jsx";
import { fmtDay, fmtDuration, fmtTime, localDay } from "../format.js";

function FrameCard({ frame, current, onOpen }) {
  return (
    <button type="button" className="frame-card" aria-current={current || undefined} onClick={() => onOpen(frame.id)}>
      <img className="thumb" src={api.thumbUrl(frame.id)} alt="" loading="lazy" />
      <div className="mt-2 flex items-baseline justify-between gap-2">
        <span className="num text-[13px] font-semibold">{fmtTime(frame.captured_at)}</span>
        <span className="help num">{fmtDuration(frame.duration_s)}</span>
      </div>
      {frame.ocr_status !== "done" && <div className="help text-[11px]">OCR {frame.ocr_status}</div>}
      {frame.excerpt && <p className="help mt-1 line-clamp-2 text-[11px] leading-snug">{frame.excerpt}</p>}
    </button>
  );
}

// One session expanded: its frames as a grid plus a scrubber to walk through them.
function SessionFrames({ session, openFrame }) {
  const [frames, setFrames] = useState(null);
  const [selected, setSelected] = useState(0);
  useEffect(() => {
    let alive = true;
    api.timeline({ from: session.start, to: session.end, app: session.app, title: session.window_title, order: "asc", limit: 500 })
      .then((r) => alive && setFrames(r.frames))
      .catch(() => alive && setFrames([]));
    return () => { alive = false; };
  }, [session]);
  if (!frames) return <p className="help px-3 pb-3">Cargando capturas…</p>;
  const current = frames[selected];
  return (
    <div className="px-3 pb-3">
      {frames.length > 1 && (
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <input type="range" className="scrubber min-w-[200px] flex-1" min={0} max={frames.length - 1} value={selected} onChange={(e) => setSelected(Number(e.target.value))} aria-label="Recorrer las capturas de la sesión" />
          <span className="num text-[13px]">{current ? fmtTime(current.captured_at) : "—"} · {selected + 1}/{frames.length}</span>
          {current && <button type="button" className="btn btn-sm btn-primary" onClick={() => openFrame(current.id)}>Abrir</button>}
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        {frames.map((f, i) => <FrameCard key={f.id} frame={f} current={i === selected} onOpen={openFrame} />)}
      </div>
    </div>
  );
}

function SessionRow({ session, open, onToggle, openFrame }) {
  return (
    <li className="rounded-lg border" style={{ borderColor: open ? "var(--accent)" : "var(--line)", background: "var(--white)" }}>
      <button type="button" className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-3 py-2 text-left" onClick={onToggle} aria-expanded={open}>
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="num text-[13px] font-semibold">{fmtTime(session.start)}–{fmtTime(session.end).slice(0, 5)}</span>
            <span className="truncate text-[13px] font-semibold">{session.window_title || "(sin título)"}</span>
            <span className="help">{session.app || "app desconocida"}</span>
          </div>
          <div className="help num">{fmtDuration(session.duration_s)} · {session.count} {session.count === 1 ? "pantalla" : "pantallas"}</div>
        </div>
        <div className="hidden gap-1 sm:flex">
          {session.thumbs.map((id) => (
            <img key={id} src={api.thumbUrl(id)} alt="" loading="lazy" className="h-10 w-[72px] rounded border object-cover" style={{ borderColor: "var(--line)" }} />
          ))}
        </div>
      </button>
      {open && <SessionFrames session={session} openFrame={openFrame} />}
    </li>
  );
}

export default function Timeline() {
  const { status, openFrame, act, refresh } = useApp();
  const [days, setDays] = useState([]);
  const [day, setDay] = useState(localDay());
  const [app, setApp] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(null); // first_id of the expanded session (stable while today grows)

  useEffect(() => {
    api.days().then((d) => {
      setDays(d.days);
      if (d.days.length && !d.days.some((x) => x.day === localDay())) setDay((current) => (current === localDay() ? d.days[0].day : current));
    }).catch(() => {});
  }, [status?.frames_total]);

  const load = useCallback(async () => {
    try {
      setData(await api.sessions({ day })); // the app filter is applied client-side so the dropdown keeps every app
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, [day]);
  useEffect(() => { setOpen(null); load(); }, [load]);
  useEffect(() => {
    if (day !== localDay() || status?.state !== "watching") return undefined;
    const timer = setInterval(load, 15000); // today keeps growing
    return () => clearInterval(timer);
  }, [day, status?.state, load]);

  const dayInfo = useMemo(() => days.find((d) => d.day === day), [days, day]);
  const apps = useMemo(() => {
    const totals = new Map();
    for (const s of data?.sessions || []) totals.set(s.app, (totals.get(s.app) || 0) + s.duration_s);
    return [...totals.entries()].sort((a, b) => b[1] - a[1]);
  }, [data]);
  const sessions = useMemo(
    () => (data?.sessions || []).filter((s) => !app || s.app === app).reverse(), // newest first
    [data, app],
  );
  const shownFrames = useMemo(() => sessions.reduce((n, s) => n + s.count, 0), [sessions]);
  const shownSeconds = useMemo(() => sessions.reduce((n, s) => n + s.duration_s, 0), [sessions]);

  const deleteDay = async () => {
    if (!window.confirm(`¿Borrar definitivamente todas las capturas del ${fmtDay(day)}? No se puede deshacer.`)) return;
    await act(() => api.deleteRange(day, day), "Capturas borradas.");
    load();
    refresh();
  };

  return (
    <div>
      <PageHeader title="Línea de tiempo" description="Cada fila es una sesión: una misma ventana vista de forma continua. Despliega una sesión para recorrer sus pantallas y abrir cualquiera con su texto seleccionable.">
        <div className="flex flex-wrap items-end gap-2">
          <label className="block">
            <span className="label">Día</span>
            <input type="date" className="field field-sm" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} list="days-with-data" />
            <datalist id="days-with-data">{days.map((d) => <option key={d.day} value={d.day} />)}</datalist>
          </label>
          <label className="block">
            <span className="label">Aplicación</span>
            <select className="field field-sm" value={app} onChange={(e) => setApp(e.target.value)}>
              <option value="">Todas</option>
              {apps.map(([name, seconds]) => <option key={name} value={name}>{name || "(desconocida)"} · {fmtDuration(seconds)}</option>)}
            </select>
          </label>
        </div>
      </PageHeader>

      {days.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1">
          {days.slice(0, 14).map((d) => (
            <button key={d.day} type="button" className={`btn btn-sm ${d.day === day ? "btn-primary" : ""}`} onClick={() => setDay(d.day)}>
              {fmtDay(d.day)} <span className="num opacity-70">{d.frames}</span>
            </button>
          ))}
        </div>
      )}

      {error && <p className="mb-4" style={{ color: "var(--danger-ink)" }}>{error}</p>}
      {data && sessions.length === 0 ? (
        <Empty title={days.length ? "Sin capturas ese día" : "Todavía no hay capturas"}>
          {days.length ? "Elige otro día o quita el filtro de aplicación." : status?.state === "watching" ? "Argus está mirando: en unos segundos aparecerá la primera pantalla." : "Activa la captura en Ajustes o reanuda la grabación."}
        </Empty>
      ) : data && (
        <>
          <p className="help mb-3">
            {sessions.length} sesiones · {shownFrames} pantallas · {fmtDuration(shownSeconds)} en pantalla
            {dayInfo ? ` · ${dayInfo.hidden} momentos ocultos por exclusiones` : ""}
          </p>
          <ul className="grid gap-2">
            {sessions.map((s) => (
              <SessionRow key={s.first_id} session={s} open={open === s.first_id} onToggle={() => setOpen(open === s.first_id ? null : s.first_id)} openFrame={openFrame} />
            ))}
          </ul>
          <div className="mt-4">
            <button type="button" className="btn btn-danger btn-sm" onClick={deleteDay}>Borrar este día</button>
          </div>
        </>
      )}
    </div>
  );
}
