import { test } from "node:test";
import assert from "node:assert/strict";
import { addRefreshHandler, buildContext, installCopilot, onTurnEnd, parseRoute, readViewStates, setViewState } from "./src/copilot-context.js";

test('import view preserves unsaved paths and identifies source records without OCR content', async () => {
  const context = await buildContext({hash:'#/importar', states:{'screenshot-import':{
    paths:['D:/archive'], recursive:true, imported_ids:[7]}},
    getFrame:async () => ({id:7,window_title:'receipt.png',origin:'import',time_basis:'file_mtime',
      source_path:'D:/archive/receipt.png',pinned:true,text:'OCR CONTENT SHOULD NOT ENTER CONTEXT'})});
  assert.equal(context.view.page,'screenshot-import');
  assert.deepEqual(context.view.editor.fields,{paths:['D:/archive'],recursive:true});
  assert.equal(context.active_objects[0].origin,'import');
  assert.equal(context.active_objects[0].source_path,'D:/archive/receipt.png');
  assert.equal('text' in context.active_objects[0],false);
});

const frame = { id: 41, window_title: "Quarterly report - Editor", app: "code", captured_at: "2026-10-12T09:15:00", duration_s: 30, ocr_status: "done", monitor: 1, pinned: true, text: "SECRET OCR TEXT" };
const days = { days: [{ day: "2026-10-12", frames: 12, hidden: 2, seconds: 600 }] };
const settings = { enabled: true, private: false, interval_s: 5, capture_scope: "active", ocr_backend: "auto", retention_days: 30, storage_cap_mb: 2000, visual_search: false };
const exclusions = { exclusions: [{ id: 3, kind: "app", pattern: "keepass*", enabled: 1 }, { id: 4, kind: "title", pattern: "incognito", enabled: 0 }] };
const deps = {
  getFrame: async (id) => { if (Number(id) !== 41 && Number(id) !== 42) throw new Error("Frame not found."); return { ...frame, id: Number(id) }; },
  getDays: async () => days,
  getSessions: async () => ({ sessions: [{ first_id: 40, app: 'code', window_title: 'Current native session', count: 4 }] }),
  getSettings: async () => settings,
  getExclusions: async () => exclusions,
};
const ids = (ctx) => ctx.active_objects.map((o) => `${o.kind}:${o.object_id}`);

test('cached sessions and search hits disappear when native records are removed', async () => {
  const removed = { ...deps, getDays: async () => ({ days: [] }), getSessions: async () => ({ sessions: [] }), getFrame: async () => { throw new Error('404'); } };
  const timeline = await buildContext({ hash: '#/linea', states: { timeline: { day: '2026-10-12', open_session: { first_id: 999, count: 1 } }, 'timeline-session': { session: 999, frame_id: 999 } }, ...removed });
  assert.deepEqual(timeline.active_objects, []);
  assert.equal(timeline.view.day, '2026-10-12');
  const search = await buildContext({ hash: '#/buscar', states: { search: { ran: { q: 'current query' }, hits: [{ id: 999 }], draft: { q: 'pending query' } } }, ...removed });
  assert.deepEqual(ids(search), ['search:current query']);
  assert.equal(search.view.editor.fields.q, 'pending query');
});

test('cached sessions and search hits use metadata read from native records', async () => {
  let params;
  const timeline = await buildContext({ hash: '#/linea', states: { timeline: { day: '2026-10-12', app: 'code', open_session: { first_id: 40, window_title: 'Stale session title', count: 99 } } }, ...deps, getSessions: async value => { params = value; return { sessions: [{ first_id: 40, window_title: 'Native new session title', count: 2 }] }; } });
  assert.deepEqual(params, { day: '2026-10-12', app: 'code' });
  const session = timeline.active_objects.find(o => o.kind === 'session');
  assert.equal(session.title, 'Native new session title');assert.equal(session.count, 2);
  const search = await buildContext({ hash: '#/buscar', states: { search: { ran: { q: 'current query' }, hits: [{ id: 41, window_title: 'Stale hit title' }] } }, ...deps });
  assert.equal(search.active_objects.find(o => o.kind === 'frame').title, frame.window_title);
});

test("route parsing maps the Spanish routes to page names and defaults to the timeline", () => {
  assert.equal(parseRoute("").page, "timeline");
  assert.equal(parseRoute("#/buscar").page, "search");
  assert.equal(parseRoute("#/actividad?x=1").page, "activity");
  assert.equal(parseRoute("#/ajustes").page, "settings");
});

test("timeline: the day, the open session and the selected capture are real objects", async () => {
  const states = {
    timeline: { day: "2026-10-12", app: "code", open_session: { first_id: 40, app: "code", window_title: "Quarterly report - Editor", start: "2026-10-12T09:00:00", end: "2026-10-12T09:20:00", count: 4, duration_s: 1200 } },
    "timeline-session": { session: 40, frame_id: 42, index: 2, total: 4 },
  };
  const ctx = await buildContext({ hash: "#/linea", states, ...deps });
  assert.deepEqual(ids(ctx), ["day:2026-10-12", "session:40", "frame:42"]);
  assert.equal(ctx.view.page, "timeline");
  assert.equal(ctx.view.day, "2026-10-12");
  assert.equal(ctx.view.app_filter, "code");
  assert.equal(ctx.view.selected_frame_id, "42");
  assert.equal(ctx.active_objects[1].count, 4);
});

test("a scrubber frame that belongs to another session is ignored", async () => {
  const states = { timeline: { day: "2026-10-12", open_session: { first_id: 40, app: "x", count: 1 } }, "timeline-session": { session: 99, frame_id: 42 } };
  assert.deepEqual(ids(await buildContext({ hash: "", states, ...deps })), ["day:2026-10-12", "session:40"]);
});

test("the open capture dialog adds the frame on any page and never leaks the recognised text", async () => {
  const ctx = await buildContext({ hash: "#/actividad", states: { viewer: { frame_id: 41 }, activity: { from: "2026-10-12", to: "2026-10-12", total_seconds: 600, top_apps: [{ app: "code", seconds: 500 }] } }, ...deps });
  assert.deepEqual(ids(ctx), ["frame:41", "period:2026-10-12..2026-10-12"]);
  assert.equal(ctx.active_objects[0].pinned, true);
  assert.equal(ctx.view.frame_id, "41");
  assert.ok(!JSON.stringify(ctx).includes("SECRET OCR TEXT"));
});

test("search: the executed query, its best moments and the unsaved form", async () => {
  const states = {
    search: {
      ran: { q: "invoice", mode: "both", from: "", to: "", app: "", moments_total: 7 },
      hits: [{ id: 41, window_title: "Mail", app: "outlook", first_at: "2026-10-12T08:00:00" }, { id: 42, window_title: "Bank", app: "chrome", first_at: "2026-10-12T08:30:00" }],
      draft: { q: "invoice 2026", mode: "text", from: "", to: "", app: "" },
    },
  };
  const ctx = await buildContext({ hash: "#/buscar", states, ...deps });
  assert.deepEqual(ids(ctx), ["search:invoice", "frame:41", "frame:42"]);
  assert.equal(ctx.view.search.moments_total, 7);
  assert.deepEqual(ctx.view.editor, { kind: "search-form", dirty: true, fields: { q: "invoice 2026", mode: "text" } });
  const similar = await buildContext({ hash: "#/buscar", states: { search: { ran: { similar_to: 41, from: "", to: "", app: "" }, hits: [] } }, ...deps });
  assert.deepEqual(ids(similar), ["similar_search:41"]);
});

test("search before any query yields no object and no editor", async () => {
  const ctx = await buildContext({ hash: "#/buscar", states: { search: { ran: null, hits: [], draft: null } }, ...deps });
  assert.deepEqual(ctx.active_objects, []);
  assert.equal(ctx.view.editor, undefined);
});

test("settings: the settings object, the rules and the unsaved fields", async () => {
  const states = {
    "settings-field:interval_s": { name: "interval_s", saved: 5, draft: "12" },
    "settings-exclusion-form": { kind: "app", pattern: "slack" },
  };
  const ctx = await buildContext({ hash: "#/ajustes", states, ...deps });
  assert.deepEqual(ids(ctx), ["settings:argus-settings", "exclusion:3", "exclusion:4"]);
  assert.equal(ctx.active_objects[0].interval_s, 5);
  assert.equal(ctx.active_objects[1].enabled, true);
  assert.equal(ctx.active_objects[2].enabled, false);
  assert.deepEqual(ctx.view.editor, { kind: "settings-form", dirty: true, fields: { interval_s: { saved: 5, draft: "12" } } });
  assert.equal(ctx.view.editors.length, 2);
  assert.deepEqual(ctx.view.editors[1].fields, { kind: "app", pattern: "slack" });
  const onlyForm = await buildContext({ hash: "#/ajustes", states: { "settings-exclusion-form": { kind: "title", pattern: "x" } }, ...deps });
  assert.equal(onlyForm.view.editor.kind, "exclusion-form");
  assert.equal(onlyForm.view.editors, undefined);
});

test("missing captures, failing reads and empty views never throw and yield no objects", async () => {
  const broken = { getFrame: async () => { throw new Error("down"); }, getDays: async () => { throw new Error("down"); }, getSettings: async () => { throw new Error("down"); }, getExclusions: async () => { throw new Error("down"); } };
  for (const hash of ["", "#/linea", "#/buscar", "#/actividad", "#/ajustes", "#/nada"]) {
    const ctx = await buildContext({ hash, states: { viewer: { frame_id: 9999 }, timeline: { day: "2026-01-01", open_session: null } }, ...broken });
    assert.deepEqual(ctx.active_objects, [], hash);
    assert.ok(ctx.view.page);
  }
  const gone = await buildContext({ hash: "", states: { viewer: { frame_id: 9999 } }, ...deps });
  assert.deepEqual(gone.active_objects, []);
  assert.deepEqual((await buildContext({ hash: "#/ajustes", ...deps })).view.editor, undefined);
});

test("view states are a registry: set, replace, clear", () => {
  const registry = new Map();
  setViewState("a", { x: 1 });
  assert.deepEqual(readViewStates(registry), {});
  assert.deepEqual(readViewStates().a, { x: 1 });
  setViewState("a", null);
  assert.equal(readViewStates().a, undefined);
});

test("turn end (event and callback) refreshes every registered view once", async () => {
  const target = new EventTarget();
  installCopilot(target);
  assert.equal(typeof target.hoardCopilot.context, "function");
  assert.equal(typeof target.hoardCopilot.onTurnEnd, "function");
  let a = 0;
  let b = 0;
  const offA = addRefreshHandler(() => { a += 1; });
  addRefreshHandler(() => { b += 1; });
  addRefreshHandler(() => { throw new Error("a broken view must not stop the others"); });
  target.dispatchEvent(new Event("hoard:copilot-turn-end"));
  onTurnEnd();
  await new Promise((r) => setTimeout(r, 400));
  assert.deepEqual([a, b], [1, 1]);
  offA();
  onTurnEnd();
  await new Promise((r) => setTimeout(r, 400));
  assert.deepEqual([a, b], [1, 2]);
});
