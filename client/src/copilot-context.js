// What the shared assistant panel asks this app for: the real objects open in the current view (a capture, a session, a search,
// a day, the settings and exclusion rules) and the unsaved form fields, plus a way to refresh the open view when the assistant
// finishes a turn. Nothing here renders anything. Recognised screen text is never sent: the assistant reads it with its own tools.
import { api } from "./api.js";

const PAGE_NAMES = { linea: "timeline", buscar: "search", importar: "screenshot-import", actividad: "activity", ajustes: "settings" };
const MAX_HITS = 5;
const MAX_RULES = 12;

// ---- what each mounted view reports about itself ------------------------------------------------------------------------
const views = new Map();

// A view (or the frame dialog) publishes a plain-data snapshot of what it shows; null removes it.
export function setViewState(key, snapshot) {
  if (snapshot === null || snapshot === undefined) views.delete(key);
  else views.set(key, snapshot);
}

export function readViewStates(source = views) {
  return Object.fromEntries(source);
}

export function parseRoute(hash) {
  const [path] = String(hash || "").replace(/^#\/?/, "").split("?");
  const first = path.split("/").filter(Boolean)[0] || "linea";
  return { path: first, page: PAGE_NAMES[first] || first };
}

const pick = (source, keys) => Object.fromEntries(keys.filter((k) => source?.[k] !== undefined && source[k] !== null && source[k] !== "").map((k) => [k, source[k]]));

export const frameObject = (f) => ({
  kind: "frame",
  object_id: String(f.id),
  title: f.window_title || "(sin titulo)",
  ...pick(f, ["app", "captured_at", "duration_s", "ocr_status", "monitor", "origin", "time_basis", "source_path"]),
  ...(f.pinned ? { pinned: true } : {}),
});

export const sessionObject = (s) => ({
  kind: "session",
  object_id: String(s.first_id),
  title: s.window_title || "(sin titulo)",
  ...pick(s, ["app", "start", "end", "count", "duration_s"]),
});

const dayObject = (d) => ({ kind: "day", object_id: d.day, title: d.day, ...pick(d, ["frames", "hidden", "seconds"]) });

async function safe(fn) {
  try { return await fn(); } catch { return null; }
}

const dirtyFields = (states) => {
  const fields = {};
  for (const [key, snap] of Object.entries(states)) {
    if (!key.startsWith("settings-field:") || !snap) continue;
    fields[snap.name] = { saved: snap.saved, draft: snap.draft };
  }
  return fields;
};

// Pure core (dependencies injected so it can be tested): never throws; unknown or removed ids yield no object.
export async function buildContext({ hash, states = {}, getFrame, getDays, getSessions, getSettings, getExclusions }) {
  const route = parseRoute(hash);
  const active = [];
  const seen = new Set();
  const add = (object) => { const key = `${object.kind}:${object.object_id}`; if (!seen.has(key)) { seen.add(key); active.push(object); } };
  const view = { page: route.page };
  const viewer = states.viewer;

  if (viewer?.frame_id) {
    const frame = await safe(() => getFrame(viewer.frame_id));
    if (frame?.id) { add(frameObject(frame)); view.frame_id = String(frame.id); }
  }

  if (route.page === "timeline") {
    const t = states.timeline;
    if (t?.day) {
      view.day = t.day;
      if (t.app) view.app_filter = t.app;
      const days = await safe(() => getDays());
      const info = (days?.days || []).find((d) => d.day === t.day);
      if (info) add(dayObject(info));
    }
    if (t?.open_session) {
      const sessions = await safe(() => getSessions({ day: t.day, app: t.app }));
      const session = (sessions?.sessions || []).find((s) => String(s.first_id) === String(t.open_session.first_id));
      if (session) add(sessionObject(session));
      const sel = states["timeline-session"];
      if (session && sel?.frame_id && String(sel.session) === String(session.first_id)) {
        const frame = await safe(() => getFrame(sel.frame_id));
        if (frame?.id) { add(frameObject(frame)); view.selected_frame_id = String(frame.id); }
      }
    }
  } else if (route.page === "search") {
    const s = states.search;
    if (s?.ran) {
      view.search = pick(s.ran, ["q", "mode", "from", "to", "app", "similar_to", "moments_total"]);
      if (s.ran.q) add({ kind: "search", object_id: s.ran.q, title: s.ran.q, ...pick(s.ran, ["mode", "from", "to", "app", "moments_total"]) });
      if (s.ran.similar_to) add({ kind: "similar_search", object_id: String(s.ran.similar_to), title: `Similar to capture ${s.ran.similar_to}` });
      for (const hit of (s.hits || []).slice(0, MAX_HITS)) {
        if (!hit?.id) continue;
        const frame = await safe(() => getFrame(hit.id));
        if (frame?.id) add(frameObject(frame));
      }
    }
    if (s?.draft && (s.draft.q || s.draft.from || s.draft.to || s.draft.app)) {
      view.editor = { kind: "search-form", dirty: true, fields: pick(s.draft, ["q", "mode", "from", "to", "app"]) };
    }
  } else if (route.page === "screenshot-import") {
    const imported = states["screenshot-import"];
    if (imported?.paths?.length) {
      view.editor = { kind: "screenshot-import-form", dirty: true, fields: { paths: imported.paths, recursive: imported.recursive } };
    }
    for (const id of (imported?.imported_ids || []).slice(0, MAX_HITS)) {
      const frame = await safe(() => getFrame(id));
      if (frame?.id) add(frameObject(frame));
    }
  } else if (route.page === "activity") {
    const a = states.activity;
    if (a?.from && a?.to) {
      view.range = { from: a.from, to: a.to };
      add({ kind: "period", object_id: `${a.from}..${a.to}`, title: a.from === a.to ? a.from : `${a.from} - ${a.to}`, ...pick(a, ["total_seconds", "top_apps"]) });
    }
  } else if (route.page === "settings") {
    const settings = await safe(() => getSettings());
    if (settings) add({ kind: "settings", object_id: "argus-settings", title: "Argus settings", ...pick(settings, ["enabled", "private", "interval_s", "capture_scope", "ocr_backend", "retention_days", "storage_cap_mb", "visual_search"]) });
    const rules = await safe(() => getExclusions());
    for (const r of (rules?.exclusions || []).slice(0, MAX_RULES)) add({ kind: "exclusion", object_id: String(r.id), title: r.pattern, enabled: Boolean(r.enabled), rule_kind: r.kind });
    const fields = dirtyFields(states);
    const form = states["settings-exclusion-form"];
    if (Object.keys(fields).length) view.editor = { kind: "settings-form", dirty: true, fields };
    if (form) view.editors = [...(view.editor ? [view.editor] : []), { kind: "exclusion-form", object_id: null, dirty: true, fields: form }];
    if (!view.editor && view.editors) { view.editor = view.editors[0]; delete view.editors; }
  }
  return { active_objects: active, view };
}

export function context() {
  return buildContext({
    hash: globalThis.window?.location?.hash,
    states: readViewStates(),
    getFrame: (id) => api.frame(id),
    getDays: () => api.days(),
    getSessions: (params) => api.sessions(params),
    getSettings: () => api.settings(),
    getExclusions: () => api.exclusions(),
  });
}

// ---- refresh when the assistant finishes a turn -------------------------------------------------------------------------
const handlers = new Set();
let timer = null;

function scheduleRefresh() {
  clearTimeout(timer);
  timer = setTimeout(() => { for (const fn of [...handlers]) { try { fn(); } catch { /* a refresh must never break the page */ } } }, 250);
}

// A view registers what "reload what is on screen" means for it (it keeps typed form fields untouched).
export function addRefreshHandler(fn) {
  handlers.add(fn);
  return () => handlers.delete(fn);
}

export const onTurnEnd = () => scheduleRefresh();

// Once at start: the object the launcher looks for, and the window event it dispatches on turn end (the debounce merges the two).
export function installCopilot(target = globalThis.window) {
  if (!target || target.hoardCopilot) return;
  target.hoardCopilot = { context, onTurnEnd };
  target.addEventListener("hoard:copilot-turn-end", scheduleRefresh);
}
