import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { PageHeader } from "../components/ui.jsx";
import { fmtDateTime } from "../format.js";
import { useCopilotRefresh, useCopilotView } from "../copilot-view.js";

async function request(path, init = {}) {
  const response = await fetch(path, init);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || result.detail || `HTTP ${response.status}`);
  return result;
}

export default function Importar() {
  const { openFrame, refresh } = useApp();
  const [paths, setPaths] = useState("");
  const [recursive, setRecursive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);
  const load = useCallback(() => request("/api/imports").then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useCopilotRefresh(load);
  useCopilotView("screenshot-import", { paths: paths.split("\n").map((p) => p.trim()).filter(Boolean), recursive, imported_ids: result?.frames.map((f) => f.id) || [] });

  const perform = async (action) => {
    setBusy(true); setError("");
    try { setResult(await action()); await load(); await refresh(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const importPaths = (event) => {
    event.preventDefault();
    const selected = paths.split("\n").map((p) => p.trim()).filter(Boolean);
    perform(() => request("/api/imports", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths: selected, recursive }) }));
  };
  const upload = (event) => {
    const files = [...(event.target.files || [])];
    event.target.value = "";
    if (!files.length) return;
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    body.append("modified", JSON.stringify(files.map((file) => file.lastModified / 1000)));
    perform(() => request("/api/imports/upload", { method: "POST", body }));
  };
  const more = async () => {
    setBusy(true); setError("");
    try {
      const next = await request(`/api/imports?before=${data.next_before}`);
      setData((previous) => ({ ...next, frames: [...previous.frames, ...next.frames] }));
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  return (
    <div>
      <PageHeader title="Importar capturas" description="Busca el texto y las imágenes de capturas que ya tienes guardadas. El original se conserva y las importadas se fijan para que la limpieza automática no las borre." />
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <label className="btn btn-primary relative overflow-hidden">Elegir imágenes<input className="absolute inset-0 opacity-0 cursor-pointer" type="file" multiple accept="image/png,image/jpeg,image/webp,image/bmp" disabled={busy} onChange={upload} /></label>
        <span className="help">PNG, JPEG, WebP y BMP · lectura local</span>
      </div>
      <form onSubmit={importPaths} className="grid gap-3 max-w-3xl">
        <label><span className="label">Archivos o carpetas por ruta, uno por línea</span><textarea className="field w-full" rows={3} value={paths} onChange={(e) => setPaths(e.target.value)} spellCheck={false} /></label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={recursive} onChange={(e) => setRecursive(e.target.checked)} />Incluir subcarpetas</label>
        <button className="btn justify-self-start" type="submit" disabled={busy || !paths.trim()}>{busy ? "Importando…" : "Importar rutas"}</button>
      </form>
      <p className="help mt-4 max-w-3xl">La fecha es la de modificación del archivo salvo que indiques otra al importar por MCP. Estas imágenes no se cuentan como tiempo observado en una aplicación. El OCR se procesa en segundo plano; pulsa Actualizar para consultar el texto nuevo.</p>
      {error && <p className="error mt-3" role="alert">{error}</p>}
      {result && <div role="status" className="mt-4"><p>{result.imported} importadas · {result.duplicates} ya estaban guardadas · {result.queue_depth} en cola OCR</p>{result.errors?.map((item, index) => <p key={index} className="help break-words">{item.source}: {item.error}</p>)}</div>}
      <div className="flex flex-wrap items-center justify-between gap-3 mt-6 mb-3"><h2 className="font-semibold">Capturas importadas</h2><button type="button" className="btn" disabled={busy} onClick={load}>Actualizar</button></div>
      {data?.frames.length === 0 && <p className="help">Todavía no hay capturas importadas.</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {data?.frames.map((frame) => <button type="button" key={frame.id} className="frame-card min-w-0 text-left" onClick={() => openFrame(frame.id)}>
          <img src={api.thumbUrl(frame.id)} alt={frame.window_title} loading="lazy" className="w-full object-contain" />
          <div className="p-3"><div className="font-semibold break-words">{frame.window_title}</div><div className="help">{fmtDateTime(frame.captured_at)} · {frame.ocr_status === "done" ? "Texto disponible" : "OCR " + frame.ocr_status}</div><p className="help break-words">{frame.excerpt || "Sin texto reconocido todavía"}</p></div>
        </button>)}
      </div>
      {data?.next_before && <button type="button" className="btn mt-4" disabled={busy} onClick={more}>Cargar más</button>}
    </div>
  );
}
