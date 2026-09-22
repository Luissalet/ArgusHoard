import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { Banner, Toast } from "./components/ui.jsx";
import FrameViewer from "./components/FrameViewer.jsx";
import Timeline from "./pages/Timeline.jsx";
import Buscar from "./pages/Buscar.jsx";
import Actividad from "./pages/Actividad.jsx";
import Ajustes from "./pages/Ajustes.jsx";

const PAGES = [
  { path: "linea", label: "Línea de tiempo", icon: "M3 12h18M7 12v-4m5 4v-7m5 7v-2M3 17h18", component: Timeline },
  { path: "buscar", label: "Buscar", icon: "M11 4a7 7 0 100 14 7 7 0 000-14zM20 20l-4-4", component: Buscar },
  { path: "actividad", label: "Actividad", icon: "M4 20V10m5 10V4m5 16v-8m5 8V7", component: Actividad },
  { path: "ajustes", label: "Ajustes", icon: "M12 8a4 4 0 100 8 4 4 0 000-8zM4 12h2m12 0h2M12 4v2m0 12v2", component: Ajustes },
];

const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

function useHashRoute() {
  const read = () => (window.location.hash.replace(/^#\/?/, "").split("/")[0] || "linea");
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

function Icon({ d }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export default function App() {
  const route = useHashRoute();
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const [viewer, setViewer] = useState(null); // frame id open in the dialog

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.status());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  const notify = useCallback((message) => setToast(message), []);
  const act = useCallback(
    async (fn, okMessage) => {
      try {
        const result = await fn();
        if (okMessage) setToast(okMessage);
        await refresh();
        return result;
      } catch (e) {
        setToast(e.message);
        return null;
      }
    },
    [refresh],
  );
  const openFrame = useCallback((id) => setViewer(id), []);
  const value = useMemo(() => ({ status, refresh, notify, act, openFrame }), [status, refresh, notify, act, openFrame]);

  const page = PAGES.find((p) => p.path === route) || PAGES[0];
  const Component = page.component;

  return (
    <AppContext.Provider value={value}>
      <div className="min-h-dvh md:grid md:grid-cols-[224px_minmax(0,1fr)]">
        <aside className="sticky top-0 z-10 border-b md:h-dvh md:border-b-0 md:border-r" style={{ background: "var(--sidebar)", borderColor: "var(--line)" }}>
          <div className="flex items-center gap-2 px-4 py-3 md:px-5 md:py-5">
            <span className="grid h-8 w-8 place-items-center rounded-md text-[15px] font-bold text-white" style={{ background: "var(--accent)", fontFamily: "Georgia, serif" }}>A</span>
            <div className="leading-tight">
              <div className="text-[15px] font-semibold">Argus's Hoard</div>
              <div className="help text-[11px]">Memoria de pantalla</div>
            </div>
          </div>
          <nav aria-label="Secciones" className="flex gap-1 overflow-x-auto px-3 pb-2 md:flex-col md:px-3">
            {PAGES.map((p) => (
              <a key={p.path} href={`#/${p.path}`} className="nav-link shrink-0 text-[13px]" aria-current={p.path === page.path ? "page" : undefined}>
                <Icon d={p.icon} />
                {p.label}
              </a>
            ))}
          </nav>
          {status && (
            <div className="hidden px-5 pt-4 md:block">
              <div className="help text-[11px]">Hoy</div>
              <div className="text-[13px]"><span className="num font-semibold">{status.today.frames}</span> capturas · <span className="num">{status.today.hidden}</span> ocultas</div>
              <div className="help text-[11px] mt-2">Disco</div>
              <div className="text-[13px] num">{(status.disk_usage_bytes / 1024 / 1024).toFixed(0)} MB de {status.storage_cap_mb} MB</div>
            </div>
          )}
        </aside>
        <main className="min-w-0 px-4 py-4 md:px-10 md:py-8">
          {error && (
            <div className="mb-4 rounded-md border p-4 text-[13px]" style={{ background: "var(--danger-bg)", color: "var(--danger-ink)", borderColor: "var(--danger-line)" }} role="alert">
              No se pudo contactar con Argus: {error}. <button type="button" className="btn-link" onClick={refresh}>Reintentar</button>
            </div>
          )}
          <div className="mb-5">
            <Banner
              status={status}
              onPause={() => act(api.pause, "Captura en pausa.")}
              onResume={() => act(api.resume, "Argus vuelve a mirar.")}
              onPrivate={(v) => act(() => api.setPrivate(v), v ? "Modo privado activado." : "Modo privado desactivado.")}
            />
          </div>
          {status ? <Component key={page.path} /> : !error && <p className="help p-8">Cargando…</p>}
        </main>
      </div>
      {viewer && <FrameViewer frameId={viewer} onClose={() => setViewer(null)} onNavigate={setViewer} />}
      <Toast message={toast} onClose={() => setToast(null)} />
    </AppContext.Provider>
  );
}
