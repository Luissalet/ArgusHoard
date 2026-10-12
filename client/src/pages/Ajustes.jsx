import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { PageHeader, Switch } from "../components/ui.jsx";
import { fmtBytes, fmtDateTime, fmtDuration, STATE_LABEL } from "../format.js";
import { useCopilotRefresh, useCopilotView } from "../copilot-view.js";

const OCR_OPTIONS = [
  { value: "auto", label: "Automático (winocr si existe, si no rapidocr)" },
  { value: "winocr", label: "Windows OCR (winocr) — rápido, solo Windows" },
  { value: "rapidocr", label: "RapidOCR (ONNX, CPU) — multiplataforma" },
  { value: "tesseract", label: "Tesseract (pytesseract)" },
];

function Row({ label, help, children }) {
  return (
    <div className="grid gap-2 py-3 md:grid-cols-[minmax(0,1fr)_260px] md:items-center" style={{ borderTop: "1px solid var(--line)" }}>
      <div>
        <div className="text-[13px] font-semibold">{label}</div>
        {help && <div className="help">{help}</div>}
      </div>
      <div className="flex items-center justify-end gap-2">{children}</div>
    </div>
  );
}

function NumberField({ name, value, onCommit, min, max, step = 1, suffix }) {
  const [draft, setDraft] = useState(String(value));
  const focused = useRef(false);
  const previous = useRef(String(value));
  // A new saved value (the assistant changed it) replaces the field unless the user is typing in it.
  useEffect(() => {
    const next = String(value);
    setDraft((current) => (current === previous.current || !focused.current ? next : current));
    previous.current = next;
  }, [value]);
  useCopilotView(`settings-field:${name}`, draft !== String(value) ? { name, saved: value, draft } : null);
  const commit = () => {
    const n = Number(draft);
    if (Number.isFinite(n) && n !== value) onCommit(n);
  };
  return (
    <label className="flex items-center gap-2">
      <input type="number" className="field field-sm w-28 text-right num" value={draft} min={min} max={max} step={step} onChange={(e) => setDraft(e.target.value)} onFocus={() => { focused.current = true; }} onBlur={() => { focused.current = false; commit(); }} onKeyDown={(e) => e.key === "Enter" && commit()} />
      {suffix && <span className="help">{suffix}</span>}
    </label>
  );
}

// Visual search: the CPU image model that lets you find a screen by how it looked.
function VisualSection({ settings, save, act }) {
  const [v, setV] = useState(null);
  const load = () => api.visualStatus().then(setV).catch(() => {});
  useEffect(() => {
    load();
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, []);
  if (!v) return null;
  const dl = v.download || {};
  const downloading = dl.state === "downloading";
  const pct = dl.total ? Math.round((100 * dl.done) / dl.total) : 0;
  const percent = v.total ? Math.round((100 * v.indexed) / v.total) : 0;
  return (
    <section className="panel-white mb-5" data-testid="visual-section">
      <h2 className="text-[17px] font-semibold">Búsqueda visual</h2>
      <p className="help">Encuentra una pantalla describiendo cómo se veía («la gráfica azul», «código en fondo oscuro»). Un modelo pequeño (CLIP, solo CPU, sin GPU) convierte cada captura guardada en un vector; se indexa en segundo plano, con prioridad baja y solo cuando el OCR está libre. Al borrar una captura se borra su vector.</p>
      <Row label="Búsqueda visual activada" help={v.available ? "Apagada, no se indexan capturas nuevas y Buscar usa solo texto." : "Se activará sola cuando descargues el modelo."}>
        <Switch checked={settings.visual_search} label="Búsqueda visual activada" onChange={(on) => save({ visual_search: on })} />
      </Row>
      <Row label="Modelo" help={`${v.model} · ${v.device.toUpperCase()} · ${v.threads} hilo${v.threads === 1 ? "" : "s"} · ${v.model_dir}`}>
        {v.available
          ? <span className="num">{fmtBytes(v.model_bytes)} en disco</span>
          : downloading
            ? <span className="num">Descargando {dl.file || ""} {pct}%</span>
            : <button type="button" className="btn btn-sm btn-primary" onClick={() => act(api.visualDownload, "Descargando el modelo…").then(load)}>Descargar modelo (≈ 300 MB)</button>}
      </Row>
      {dl.state === "error" && <p className="help" style={{ color: "var(--danger-ink)" }}>No se pudo descargar: {dl.error}</p>}
      <Row label="Capturas indexadas" help={v.active ? (v.indexing ? "Indexando ahora…" : v.pending ? "Pendientes: se indexan cuando el equipo está libre." : "Al día.") : "Sin indexar mientras la búsqueda visual no esté activa."}>
        <span className="num" data-testid="visual-count">{v.indexed} de {v.total} ({percent}%){v.ms_per_frame != null ? ` · ${v.ms_per_frame} ms/captura` : ""}</span>
      </Row>
      {v.available && (
        <Row label="Volver a indexar" help="Borra todos los vectores y vuelve a calcularlos (por si cambias de modelo).">
          <button type="button" className="btn btn-sm" onClick={() => act(api.visualReindex, "Se reindexarán todas las capturas.").then(load)}>Reindexar</button>
        </Row>
      )}
      {v.last_error && <p className="help" style={{ color: "var(--danger-ink)" }}>{v.last_error}</p>}
    </section>
  );
}

export default function Ajustes() {
  const { status, act, refresh } = useApp();
  const [settings, setSettings] = useState(null);
  const [rules, setRules] = useState([]);
  const [kind, setKind] = useState("app");
  const [pattern, setPattern] = useState("");
  const [testApp, setTestApp] = useState("");
  const [testTitle, setTestTitle] = useState("");
  const [testResult, setTestResult] = useState(null);

  const loadRules = () => api.exclusions().then((r) => setRules(r.exclusions)).catch(() => {});
  useEffect(() => { api.settings().then(setSettings).catch(() => {}); loadRules(); }, []);
  // The assistant finished a turn: reload settings and rules in place (typed fields keep what the user wrote).
  useCopilotRefresh(() => { api.settings().then(setSettings).catch(() => {}); loadRules(); });
  useCopilotView("settings-exclusion-form", pattern.trim() ? { kind, pattern } : null);

  const save = async (patch) => {
    const updated = await act(() => api.updateSettings(patch));
    if (updated) setSettings(updated);
  };
  const addRule = async (e) => {
    e.preventDefault();
    if (!pattern.trim()) return;
    if (await act(() => api.addExclusion(kind, pattern.trim()), "Exclusión añadida.")) { setPattern(""); loadRules(); }
  };
  const runTest = async () => {
    try { setTestResult(await api.testExclusion(testApp, testTitle)); } catch (e) { setTestResult({ error: e.message }); }
  };

  if (!settings || !status) return <p className="help">Cargando…</p>;
  const available = status.ocr_available || {};

  return (
    <div className="max-w-[900px]">
      <PageHeader title="Ajustes" description="Todo se guarda al instante. Argus solo escribe en tu disco; nada sale del ordenador." />

      <section className="panel mb-5 flex flex-wrap items-center gap-5">
        <Switch big checked={settings.private} label="Modo privado" onChange={(v) => act(() => api.setPrivate(v), v ? "Modo privado activado." : "Modo privado desactivado.").then(() => api.settings().then(setSettings))} />
        <div className="min-w-0 flex-1">
          <div className="text-[17px] font-semibold">Modo privado</div>
          <div className="help">Mientras esté activo no se captura nada, aunque la grabación esté encendida. Úsalo para contraseñas, banca o conversaciones que no quieras recordar.</div>
        </div>
      </section>

      <section className="panel-white mb-5">
        <h2 className="text-[17px] font-semibold">Estado</h2>
        <dl className="mt-3 grid gap-x-6 gap-y-1 text-[13px] sm:grid-cols-2">
          <dt className="help">Estado</dt><dd>{STATE_LABEL[status.state]}</dd>
          <dt className="help">Última captura</dt><dd>{fmtDateTime(status.last_capture_at)}</dd>
          <dt className="help">Cola de OCR</dt><dd className="num">{status.queue_depth} pendientes · {status.ocr_processed} procesadas{status.ocr_last_ms != null ? ` · última ${status.ocr_last_ms} ms` : ""}</dd>
          <dt className="help">Motor OCR en uso</dt><dd>{status.ocr_backend}</dd>
          <dt className="help">Captura / ventana activa</dt><dd>{status.capture_backend} / {status.window_backend} · {status.monitors} monitores{status.active_monitor ? `, activo #${status.active_monitor}` : ""}</dd>
          <dt className="help">Sin cambios</dt><dd>{status.idle_since ? `desde hace ${fmtDuration(status.idle_s)} (${fmtDateTime(status.idle_since)})` : "la pantalla activa está cambiando"}</dd>
          <dt className="help">Disco usado por capturas</dt><dd className="num">{fmtBytes(status.disk_usage_bytes)} de {status.storage_cap_mb} MB · libre {fmtBytes(status.disk_free_bytes)}</dd>
          <dt className="help">Capturas guardadas</dt><dd className="num">{status.frames_total} · hoy {status.today.frames} ({status.today.hidden} ocultas)</dd>
          <dt className="help">Carpeta de datos</dt><dd className="break-all">{status.data_dir}</dd>
          {status.last_error && (<><dt className="help">Último error</dt><dd style={{ color: "var(--danger-ink)" }}>{status.last_error}</dd></>)}
          {status.capture_notes?.length > 0 && (<><dt className="help">Notas</dt><dd>{status.capture_notes.join(" · ")}</dd></>)}
        </dl>
      </section>

      <section className="panel-white mb-5">
        <h2 className="text-[17px] font-semibold">Captura</h2>
        <Row label="Grabación activada" help="Apagada, Argus no captura nada ni arranca al abrir la app.">
          <Switch checked={settings.enabled} label="Grabación activada" onChange={(v) => save({ enabled: v })} />
        </Row>
        <Row label="Intervalo" help="Segundos entre capturas. Las pantallas iguales no se duplican: solo se alarga su duración.">
          <NumberField name="interval_s" value={settings.interval_s} min={1} max={600} suffix="s" onCommit={(n) => save({ interval_s: n })} />
        </Row>
        <Row label="Sensibilidad al cambio" help="Celdas de una cuadrícula 384×216 que deben cambiar para guardar una pantalla nueva. Más alto = menos capturas.">
          <NumberField name="dedupe_threshold" value={settings.dedupe_threshold} min={0} max={5000} suffix="celdas" onCommit={(n) => save({ dedupe_threshold: n })} />
        </Row>
        <Row label="Ámbito de captura" help={`Con «solo el monitor activo» se captura y se lee únicamente la pantalla donde está la ventana en primer plano (${status.monitors} monitores detectados). Si no se sabe cuál es, se usa el principal.`}>
          <select className="field field-sm" value={settings.capture_scope} onChange={(e) => save({ capture_scope: e.target.value })}>
            <option value="active">Solo el monitor con la ventana activa</option>
            <option value="all">Todos los monitores</option>
          </select>
        </Row>
        <Row label="Motor OCR" help={Object.entries(available).map(([k, v]) => `${k}: ${v.available ? "disponible" : v.reason}`).join(" · ")}>
          <select className="field field-sm" value={settings.ocr_backend} onChange={(e) => save({ ocr_backend: e.target.value })}>
            {OCR_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Row>
        <Row label="Ancho máximo de imagen" help="Las capturas se guardan en WebP reducidas a este ancho; el OCR usa la resolución original.">
          <NumberField name="image_max_width" value={settings.image_max_width} min={320} max={3840} step={64} suffix="px" onCommit={(n) => save({ image_max_width: n })} />
        </Row>
      </section>

      <VisualSection settings={settings} save={save} act={act} />

      <section className="panel-white mb-5">
        <h2 className="text-[17px] font-semibold">Retención</h2>
        <Row label="Conservar durante" help="Las capturas más antiguas se borran automáticamente (imágenes y texto). 0 = conservar siempre.">
          <NumberField name="retention_days" value={settings.retention_days} min={0} max={3650} suffix="días" onCommit={(n) => save({ retention_days: n })} />
        </Row>
        <Row label="Límite de disco" help="Al superarlo se borran primero las capturas más antiguas.">
          <NumberField name="storage_cap_mb" value={settings.storage_cap_mb} min={100} max={1000000} step={100} suffix="MB" onCommit={(n) => save({ storage_cap_mb: n })} />
        </Row>
        <div className="help pt-2">Para borrar un tramo concreto usa «Borrar este día» en la línea de tiempo o pide al asistente que borre un rango.</div>
      </section>

      <section className="panel-white mb-5">
        <h2 className="text-[17px] font-semibold">Exclusiones</h2>
        <p className="help">Las pantallas de estas aplicaciones o ventanas no se guardan ni se leen: solo se cuenta un momento «oculto».</p>
        <form onSubmit={addRule} className="mt-3 flex flex-wrap gap-2">
          <select className="field field-sm w-auto" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Tipo de regla">
            <option value="app">Aplicación (proceso)</option>
            <option value="title">Título de ventana (regex)</option>
          </select>
          <input className="field field-sm min-w-[200px] flex-1" value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder={kind === "app" ? "keepass* · banco-app · chrome" : "incógnito|private browsing"} aria-label="Patrón" />
          <button type="submit" className="btn btn-sm btn-primary" disabled={!pattern.trim()}>Añadir</button>
        </form>
        <ul className="mt-3 grid gap-1">
          {rules.length === 0 && <li className="help">Sin exclusiones. Ejemplos: <code>keepass*</code> como aplicación, <code>incógnito</code> como título.</li>}
          {rules.map((r) => (
            <li key={r.id} className="flex items-center gap-3 rounded-md px-2 py-1.5" style={{ background: "var(--soft)" }}>
              <span className="chip">{r.kind === "app" ? "app" : "título"}</span>
              <code className="min-w-0 flex-1 truncate text-[12px]">{r.pattern}</code>
              <Switch checked={r.enabled} label={`Regla ${r.pattern} activa`} onChange={(v) => act(() => api.toggleExclusion(r.id, v)).then(loadRules)} />
              <button type="button" className="btn-link text-[12px]" onClick={() => act(() => api.removeExclusion(r.id), "Exclusión eliminada.").then(loadRules)}>Quitar</button>
            </li>
          ))}
        </ul>
        <div className="mt-4 rounded-md border p-3" style={{ borderColor: "var(--line)" }}>
          <div className="text-[13px] font-semibold">¿Esta ventana se excluiría?</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <input className="field field-sm w-40" value={testApp} onChange={(e) => setTestApp(e.target.value)} placeholder="proceso, p. ej. chrome" aria-label="Proceso a comprobar" />
            <input className="field field-sm min-w-[200px] flex-1" value={testTitle} onChange={(e) => setTestTitle(e.target.value)} placeholder="título de la ventana" aria-label="Título a comprobar" />
            <button type="button" className="btn btn-sm" onClick={runTest}>Comprobar</button>
          </div>
          {testResult && (
            <p className="mt-2 text-[13px]">
              {testResult.error ? testResult.error : testResult.excluded ? <>Sí: la regla <code>{testResult.rule.pattern}</code> ({testResult.rule.kind === "app" ? "aplicación" : "título"}) la ocultaría.</> : "No: esa ventana se capturaría."}
            </p>
          )}
        </div>
      </section>
      <p className="help">Versión {status.version}. <button type="button" className="btn-link" onClick={refresh}>Actualizar estado</button></p>
    </div>
  );
}
