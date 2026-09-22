import React, { useEffect } from "react";
import { STATE_LABEL } from "../format.js";

export function Toast({ message, onClose }) {
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(onClose, 4000);
    return () => clearTimeout(timer);
  }, [message, onClose]);
  if (!message) return null;
  return (
    <div className="toast" role="status">
      {message} <button type="button" className="ml-3 underline" onClick={onClose}>Cerrar</button>
    </div>
  );
}

export function Banner({ status, onPause, onResume, onPrivate }) {
  if (!status) return null;
  const state = status.state;
  const detail =
    state === "watching"
      ? `cada ${status.interval_s} s · OCR ${status.ocr_backend}${status.queue_depth ? ` · ${status.queue_depth} en cola` : ""}`
      : state === "paused"
        ? "no se guardan capturas hasta que reanudes"
        : state === "private"
          ? "no se captura nada mientras esté activo"
          : "actívala en Ajustes para empezar a recordar";
  return (
    <div className={`banner banner-${state}`} role="status" aria-live="polite">
      <span className="dot" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        {STATE_LABEL[state]} <span className="font-normal opacity-80">· {detail}</span>
      </span>
      {state === "watching" && <button type="button" className="btn btn-sm" onClick={onPause}>Pausar</button>}
      {state === "paused" && <button type="button" className="btn btn-sm btn-primary" onClick={onResume}>Reanudar</button>}
      {state === "private" && <button type="button" className="btn btn-sm" onClick={() => onPrivate(false)}>Salir del modo privado</button>}
    </div>
  );
}

export function Switch({ checked, onChange, label, big = false }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`switch ${big ? "switch-big" : ""}`}
      onClick={() => onChange(!checked)}
    />
  );
}

export function Empty({ title, children }) {
  return (
    <div className="rounded-lg border border-dashed p-8 text-center" style={{ borderColor: "var(--field-line)" }}>
      <p className="font-semibold">{title}</p>
      <p className="help mt-1">{children}</p>
    </div>
  );
}

export function PageHeader({ title, description, children }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-[26px] font-semibold leading-tight md:text-[30px]">{title}</h1>
        {description && <p className="help mt-1 max-w-[70ch]">{description}</p>}
      </div>
      {children}
    </header>
  );
}
