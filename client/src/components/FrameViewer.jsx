import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { fmtDateTime, fmtDuration } from "../format.js";

// Text layer over the image: every OCR block is a transparent, selectable span.
function OcrLayer({ frame, size, showBoxes }) {
  if (!frame.blocks || !size.width) return null;
  const sx = size.width / frame.width;
  const sy = size.height / frame.height;
  return (
    <div className={`ocr-layer ${showBoxes ? "show-boxes" : ""}`} aria-label="Texto reconocido">
      {frame.blocks.map((b, i) => (
        <span
          key={i}
          className="ocr-block"
          style={{ left: b.x * sx, top: b.y * sy, width: b.w * sx, height: b.h * sy, fontSize: Math.max(6, b.h * sy * 0.8) }}
          title={b.text}
        >
          {b.text}
        </span>
      ))}
    </div>
  );
}

export default function FrameViewer({ frameId, onClose, onNavigate }) {
  const dialogRef = useRef(null);
  const imageRef = useRef(null);
  const [frame, setFrame] = useState(null);
  const [error, setError] = useState(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [showBoxes, setShowBoxes] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => dialog && dialog.open && dialog.close();
  }, []);

  useEffect(() => {
    let alive = true;
    setFrame(null);
    setError(null);
    api.frame(frameId).then((data) => alive && setFrame(data)).catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [frameId]);

  const measure = useCallback(() => {
    const img = imageRef.current;
    if (img) setSize({ width: img.clientWidth, height: img.clientHeight });
  }, []);
  useLayoutEffect(() => {
    measure();
    const observer = new ResizeObserver(measure);
    if (imageRef.current) observer.observe(imageRef.current);
    return () => observer.disconnect();
  }, [measure, frame]);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "ArrowLeft" && frame?.prev) onNavigate(frame.prev);
      if (event.key === "ArrowRight" && frame?.next) onNavigate(frame.next);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [frame, onNavigate]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(frame.text || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <dialog ref={dialogRef} onClose={onClose} aria-label="Detalle de la captura" onClick={(e) => e.target === dialogRef.current && onClose()}>
      <div className="flex max-h-[calc(100dvh-24px)] flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b px-4 py-3" style={{ borderColor: "var(--line)" }}>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[15px] font-semibold">{frame ? frame.window_title || "(sin título de ventana)" : "Cargando…"}</div>
            {frame && (
              <div className="help">
                {frame.app || "app desconocida"} · {fmtDateTime(frame.captured_at)} · {fmtDuration(frame.duration_s)} en pantalla · monitor {frame.monitor}
                {frame.ocr_status !== "done" && <span className="chip chip-warn ml-2">OCR: {frame.ocr_status}</span>}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="btn btn-sm" disabled={!frame?.prev} onClick={() => onNavigate(frame.prev)} aria-label="Captura anterior">← Anterior</button>
            <button type="button" className="btn btn-sm" disabled={!frame?.next} onClick={() => onNavigate(frame.next)} aria-label="Captura siguiente">Siguiente →</button>
            <button type="button" className="btn btn-sm" onClick={onClose} aria-label="Cerrar">Cerrar</button>
          </div>
        </header>
        {error && <p className="p-4" style={{ color: "var(--danger-ink)" }}>{error}</p>}
        {frame && (
          <div className="grid min-h-0 flex-1 gap-0 overflow-hidden md:grid-cols-[minmax(0,1fr)_320px]">
            <div className="min-h-0 overflow-auto p-3" style={{ background: "var(--soft)" }}>
              <div className="relative mx-auto w-fit">
                <img ref={imageRef} src={api.imageUrl(frame.id)} alt="" onLoad={measure} className="block max-h-[calc(100dvh-160px)] max-w-full select-none" draggable="false" />
                <OcrLayer frame={frame} size={size} showBoxes={showBoxes} />
              </div>
            </div>
            <aside className="flex min-h-0 flex-col border-t md:border-l md:border-t-0" style={{ borderColor: "var(--line)" }}>
              <div className="flex items-center gap-2 px-4 py-2" style={{ borderBottom: "1px solid var(--line)" }}>
                <span className="whitespace-nowrap text-[12px] font-semibold">Texto OCR</span>
                <span className="help whitespace-nowrap">({frame.blocks?.length || 0} bloques{frame.ocr_ms ? `, ${frame.ocr_ms} ms` : ""})</span>
                <span className="flex-1" />
                <button type="button" className="btn-link whitespace-nowrap text-[12px]" onClick={() => setShowBoxes((v) => !v)}>{showBoxes ? "Ocultar cajas" : "Ver cajas"}</button>
                <button type="button" className="btn-link text-[12px]" onClick={copy}>{copied ? "Copiado" : "Copiar"}</button>
              </div>
              <pre className="min-h-[120px] flex-1 overflow-auto whitespace-pre-wrap px-4 py-3 text-[12px] leading-[1.6]" style={{ fontFamily: "inherit", margin: 0 }}>
                {frame.text || (frame.ocr_status === "pending" ? "Pendiente de OCR…" : "Sin texto reconocido.")}
              </pre>
            </aside>
          </div>
        )}
      </div>
    </dialog>
  );
}
