import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Empty, PageHeader } from "../components/ui.jsx";
import { dayOffset, fmtDay, fmtDuration, localDay } from "../format.js";

const PRESETS = [
  { label: "Hoy", from: () => localDay(), to: () => localDay() },
  { label: "Ayer", from: () => dayOffset(-1), to: () => dayOffset(-1) },
  { label: "7 días", from: () => dayOffset(-6), to: () => localDay() },
  { label: "30 días", from: () => dayOffset(-29), to: () => localDay() },
];

export default function Actividad() {
  const [from, setFrom] = useState(localDay());
  const [to, setTo] = useState(localDay());
  const [data, setData] = useState(null);
  const [days, setDays] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    api.apps({ from, to }).then((d) => alive && setData(d)).catch((e) => alive && setError(e.message));
    api.days().then((d) => alive && setDays(d.days)).catch(() => {});
    return () => { alive = false; };
  }, [from, to]);

  const max = data?.apps?.[0]?.seconds || 1;

  return (
    <div>
      <PageHeader title="Actividad" description="Tiempo por aplicación calculado a partir de cuánto permaneció cada pantalla a la vista. Las exclusiones y el modo privado no cuentan.">
        <div className="flex flex-wrap items-end gap-2">
          {PRESETS.map((p) => (
            <button key={p.label} type="button" className={`btn btn-sm ${from === p.from() && to === p.to() ? "btn-primary" : ""}`} onClick={() => { setFrom(p.from()); setTo(p.to()); }}>{p.label}</button>
          ))}
          <label className="block"><span className="label">Desde</span><input type="date" className="field field-sm" value={from} onChange={(e) => e.target.value && setFrom(e.target.value)} /></label>
          <label className="block"><span className="label">Hasta</span><input type="date" className="field field-sm" value={to} onChange={(e) => e.target.value && setTo(e.target.value)} /></label>
        </div>
      </PageHeader>

      {error && <p style={{ color: "var(--danger-ink)" }}>{error}</p>}
      {data && data.apps.length === 0 && <Empty title="Sin actividad en ese periodo">Cuando Argus capture pantallas aparecerá aquí el reparto por aplicación.</Empty>}
      {data && data.apps.length > 0 && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <section className="panel-white">
            <h2 className="text-[17px] font-semibold">Por aplicación <span className="help font-normal">· {fmtDuration(data.total_seconds)} en total</span></h2>
            <ul className="mt-4 grid gap-3">
              {data.apps.map((a) => (
                <li key={a.app}>
                  <div className="flex items-baseline justify-between gap-3 text-[13px]">
                    <span className="truncate font-semibold">{a.app || "(desconocida)"}</span>
                    <span className="num help">{fmtDuration(a.seconds)} · {a.frames} pantallas</span>
                  </div>
                  <div className="bar mt-1"><span style={{ width: `${Math.max(2, (a.seconds / max) * 100)}%` }} /></div>
                  {a.top_windows.length > 0 && (
                    <ul className="mt-1 grid gap-0.5 pl-3">
                      {a.top_windows.map((w) => (
                        <li key={w.window_title} className="flex justify-between gap-3 text-[12px]">
                          <span className="help truncate">{w.window_title || "(sin título)"}</span>
                          <span className="num help shrink-0">{fmtDuration(w.seconds)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </section>
          <section className="panel-white">
            <h2 className="text-[17px] font-semibold">Por día</h2>
            <table className="mt-3 w-full text-[13px]">
              <thead>
                <tr className="help text-left text-[11px] uppercase tracking-wide">
                  <th className="pb-1 font-semibold">Día</th><th className="pb-1 text-right font-semibold">Pantallas</th><th className="pb-1 text-right font-semibold">Ocultas</th><th className="pb-1 text-right font-semibold">Tiempo</th>
                </tr>
              </thead>
              <tbody>
                {days.filter((d) => d.day >= from && d.day <= to).map((d) => (
                  <tr key={d.day} style={{ borderTop: "1px solid var(--line)" }}>
                    <td className="py-1.5">{fmtDay(d.day)}</td>
                    <td className="num py-1.5 text-right">{d.frames}</td>
                    <td className="num py-1.5 text-right">{d.hidden}</td>
                    <td className="num py-1.5 text-right">{fmtDuration(d.seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </div>
  );
}
