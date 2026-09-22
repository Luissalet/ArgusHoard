const pad = (n) => String(n).padStart(2, "0");

export function localDay(date = new Date()) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function dayOffset(days) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return localDay(date);
}

export function fmtTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function fmtDateTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  return `${localDay(date)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function fmtDay(day) {
  if (!day) return "—";
  const [y, m, d] = day.split("-");
  const date = new Date(Number(y), Number(m) - 1, Number(d));
  return date.toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

export function fmtDuration(seconds) {
  seconds = Math.round(seconds || 0);
  if (seconds < 60) return `${seconds} s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
}

export function fmtBytes(bytes) {
  if (bytes == null) return "—";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export const STATE_LABEL = {
  watching: "Argus está mirando",
  paused: "Argus está en pausa",
  private: "Modo privado: Argus no mira",
  disabled: "Captura desactivada",
};
