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
      <div className="truncate text-[12px]">{frame.window_title || <span className="help">(sin título)</span>}</div>
      <div className="help truncate text-[11px]">{frame.app || "app desconocida"}{frame.ocr_status !== "done" ? ` · OCR ${frame.ocr_status}` : ""}</div>
      {frame.excerpt && <p className="help mt-1 line-clamp-2 text-[11px] leading-snug">{frame.excerpt}</p>}
    </button>
  );
}

export default function Timeline() {
  const { status, openFrame, act, refresh } = useApp();
  const [days, setDays] = useState([]);
  const [day, setDay] = useState(localDay());
  const [app, setApp] = useState("");
  const [apps, setApps] = useState([]);
  const [frames, setFrames] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(0);

  useEffect(() => {
    api.days().then((d) => {
      setDays(d.days);
      if (d.days.length && !d.days.some((x) => x.day === localDay())) setDay(d.days[0].day);
    }).catch(() => {});
  }, [status?.frames_total]);

  const load = useCallback(async (reset) => {
    setLoading(true);
    try {
      const params = { from: day, to: day, app, limit: 120, order: "asc" };
      if (!reset && cursor) params.cursor = cursor;
      const result = await api.timeline(params);
      setFrames((prev) => (reset ? result.frames : [...prev, ...result.frames]));
      setCursor(result.next_cursor);
      if (reset) {
        setSelected(0);
        const a = await api.apps({ from: day, to: day });
        setApps(a.apps);
      }
    } finally {
      setLoading(false);
    }
  }, [day, app, cursor]);

  useEffect(() => { load(true); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [day, app]);

  const dayInfo = useMemo(() => days.find((d) => d.day === day), [days, day]);
  const current = frames[selected];

  const deleteDay = async () => {
    if (!window.confirm(`¿Borrar definitivamente todas las capturas del ${fmtDay(day)}? No se puede deshacer.`)) return;
    await act(() => api.deleteRange(day, day), "Capturas borradas.");
    load(true);
    refresh();
  };

  return (
    <div>
      <PageHeader title="Línea de tiempo" description="Cada tarjeta es una pantalla distinta y cuánto tiempo estuvo a la vista. Pulsa para ver la captura con su texto seleccionable.">
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
              {apps.map((a) => <option key={a.app} value={a.app}>{a.app || "(desconocida)"} · {fmtDuration(a.seconds)}</option>)}
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

      {frames.length === 0 && !loading ? (
        <Empty title={days.length ? "Sin capturas ese día" : "Todavía no hay capturas"}>
          {days.length ? "Elige otro día o quita el filtro de aplicación." : status?.state === "watching" ? "Argus está mirando: en unos segundos aparecerá la primera pantalla." : "Activa la captura en Ajustes o reanuda la grabación."}
        </Empty>
      ) : (
        <>
          <div className="panel mb-4 !py-3">
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="range"
                className="scrubber min-w-[200px] flex-1"
                min={0}
                max={Math.max(0, frames.length - 1)}
                value={selected}
                onChange={(e) => setSelected(Number(e.target.value))}
                aria-label="Recorrer las capturas del día"
              />
              <span className="num text-[13px]">{current ? fmtTime(current.captured_at) : "—"} · {selected + 1}/{frames.length}</span>
              {current && <button type="button" className="btn btn-sm btn-primary" onClick={() => openFrame(current.id)}>Abrir</button>}
            </div>
            {current && (
              <div className="mt-2 flex items-center gap-3">
                <img className="h-16 w-28 rounded border object-cover" style={{ borderColor: "var(--line)" }} src={api.thumbUrl(current.id)} alt="" />
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-semibold">{current.window_title || "(sin título)"}</div>
                  <div className="help truncate">{current.app || "app desconocida"} · {fmtDuration(current.duration_s)}</div>
                </div>
              </div>
            )}
            {dayInfo && <div className="help mt-2">{dayInfo.frames} pantallas · {fmtDuration(dayInfo.seconds)} en pantalla · {dayInfo.hidden} momentos ocultos por exclusiones</div>}
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {frames.map((f, i) => <FrameCard key={f.id} frame={f} current={i === selected} onOpen={openFrame} />)}
          </div>
          <div className="mt-4 flex items-center gap-3">
            {cursor && <button type="button" className="btn" disabled={loading} onClick={() => load(false)}>Cargar más</button>}
            {dayInfo && <button type="button" className="btn btn-danger btn-sm" onClick={deleteDay}>Borrar este día</button>}
          </div>
        </>
      )}
    </div>
  );
}
