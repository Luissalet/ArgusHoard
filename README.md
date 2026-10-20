> **Absorbed by [Talos's Hoard](https://github.com/Luissalet/TalosHoard).** All functions and stored data continue in the merged app. This repository is retained as historical source; its Hub entry provides compatibility only and cannot launch a standalone server. Start Talos's Hoard and explicitly enable the modules you need; all default OFF. Data and capabilities are managed through Talos's Hoard.
>
> The documentation below describes the incorporated engine. Use the linked repository for current installation and operation.

# Argus's Hoard

A private, self-hosted **screen memory** for your own Windows PC: every few
seconds Argus captures the screen, notes the active window, skips frames that
have not changed, runs OCR on the new ones and gives you a timeline, full-text
search and time-by-app — all stored locally and exposed to an assistant
("Faustus") through MCP. Think of it as a transparent, user-owned take on the
"recall" idea: you can see exactly what is stored, pause it, exclude apps,
delete ranges and cap its disk usage.

Nothing leaves the machine. There is no cloud, no telemetry and no network
call besides `127.0.0.1`.

## What is captured (be honest with yourself)

While the state is **watching**, every `interval_s` seconds (default 5):

1. The active window is read (title, process name, monitor).
2. If an **exclusion** rule matches (process name or window-title regex), nothing
   is captured or read; only a "hidden" tick is counted for that day.
3. Otherwise the screen is captured: with `capture_scope: active` (default)
   only the monitor that contains the active window (primary monitor when the
   window position is unknown); with `all`, every monitor. A frame that looks like the previous
   one for that monitor (same window, fewer than `dedupe_threshold` cells of a
   384×216 grey grid changed) is **not stored**: the previous frame's `until`
   time is extended instead. That is how durations are computed.
4. New frames are saved as WebP (max width 1280) plus a 320 px thumbnail under
   `data/frames/YYYY/MM/DD/<id>.webp` and queued for OCR. OCR never blocks
   capture; the queue depth is visible in the status.
5. OCR text and layout blocks (bounding boxes, confidence) go into SQLite with
   an FTS5 index (BM25 over text, window title and app).

Not captured: anything while **paused**, in **private mode** or with the
capture **disabled**, and anything matching an exclusion. Keystrokes, audio,
clipboard and network traffic are never touched.

## Privacy controls

- **Pause / resume** from the banner, the API or the `screen_pause` tool.
- **Private mode**: a big switch in *Ajustes* (no hotkey). Nothing is captured
  until you switch it off; it survives restarts.
- **Exclusions**: by process name (`keepass*`, `banco-app`) or window-title
  regex (`incógnito|private browsing`). Test any app/title in the settings
  page ("¿esta ventana se excluiría?").
- **Retention**: frames older than `retention_days` (default 30) are deleted —
  images and text — by a janitor that runs at start and every 10 minutes.
- **Storage cap**: when the frames folder exceeds `storage_cap_mb` the oldest
  frames are deleted first.
- **Pin a frame**: use “☆ Fijar” in its detail view to preserve it through
  automatic age or storage cleanup; unpin to restore normal cleanup. An
  explicit range deletion still removes pinned frames.
- **Delete range**: `DELETE /api/frames?from&to`, "Borrar este día" in the
  timeline, or the `screen_delete_range` tool. Permanent.

## Requirements

- Windows 10/11 (capture + active window). The whole pipeline after capture
  also runs on Linux/macOS with the fake backend for tests and demos.
- Python 3.11+ (3.13 works). Node 22 only to build the client.
- CPU is enough. With `ocr_backend: auto` the engine is `winocr`
  (Windows.Media.Ocr, about 150 ms per 1080p frame, needs
  `requirements-windows.txt`) when available. Otherwise it shares Kafka's OCR
  through the Hoard Link hub before trying `rapidocr` (ONNX on CPU) and
  `tesseract` locally. This avoids loading a second OCR model when Kafka is
  available; Windows OCR keeps its fast local path. An explicit engine choice
  still wins. `family` is also selectable through `PUT /api/settings`; frames
  travel only to that local service, as a temporary PNG removed right after.
  In auto mode, a service outage can use a cached local fallback and retry Kafka
  on later frames. Authentication or tool errors do not silently switch engines.

## Install and run (Windows)

```bat
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\pip install -r requirements-windows.txt   :: optional: winocr, pywin32
npm install
npm run build                                         :: builds the UI into argus\static
venv\Scripts\python scripts\selftest.py               :: one real capture + OCR, prints text + timings
venv\Scripts\python scripts\launch.py                 :: starts the app and opens the browser
```

`python -m argus` starts the server on `http://127.0.0.1:5183` (env
`ARGUS_PORT`/`PORT`; `PORT_STRICT=1` pins it, otherwise the next free port is
used). Data lives in `ARGUS_DATA_DIR` or `<repo>/data` (gitignored).

Other env vars: `ARGUS_CAPTURE=auto|mss|fake|none`, `ARGUS_WINDOW=auto|windows|fake|none`,
`ARGUS_AUTOSTART=0` (do not start the recorder thread), `ARGUS_VISUAL=auto|fake|none`,
`ARGUS_VISUAL_THREADS`, `ARGUS_VISUAL_DUTY` (see Visual search).

### Access from your phone (behind a tunnel)

The server binds 127.0.0.1 and only answers requests whose `Host` is `localhost`, `127.0.0.1` or `[::1]`. To reach it from your phone through a tunnel that fronts the app (a private mesh network, a reverse proxy), list the extra host names in `ARGUS_ALLOWED_HOSTS`, comma-separated, exact names or `*.suffix`: `ARGUS_ALLOWED_HOSTS=my-pc.example,*.ts.net`. Letter case is ignored and an entry without a port matches any port (write `my-pc.example:8443` to pin one); the `Origin` of API calls must resolve to one of those hosts too (any scheme or port). Cross-site *fetches* are still refused; opening the app from another page (a link, a bookmarklet, the share sheet) is a normal navigation and works.

Once opened through the tunnel, the browser offers to install it (PWA).

### Shared plumbing

The server plumbing comes from the shared Hoard Link library vendored in `argus/hoard_link/` (never edited here): host/origin guard, error handlers, `/api/health`, PWA manifest + service worker + SPA fallback, port and token files (the token is at least 32 characters), config readers, the SQLite wrapper, the agent catalogue router and the MCP bridge. Search uses its word rules and BM25 (`hoard_link.docs.textsearch`: accents folded, filler words dropped from multi-word queries, short words exact, longer ones as prefixes) and the change detector its perceptual hash (`hoard_link.docs.imaging`). `ARGUS_LOG` is no longer read: the server logs at INFO to the console and to `data/logs/argus-hoard.log` (rotating).

Development: `python scripts/dev.py` runs uvicorn `--reload` plus the Vite dev
server (proxying `/api`).

## Visual search

Besides the OCR text, Argus can search the screenshots by how they look
(`blue bar chart`, `gráfica azul`, `code on a dark background`) and find the
screens that look like one you already have. It is optional and local.

- **Model**: CLIP ViT-B/32 multilingual, 512 dimensions. The text tower is the
  multilingual DistilBERT export (int8 ONNX, about 135 MB) and the image tower is
  the ONNX vision model with fp16 weights (about 176 MB). Together about 314 MB
  to download (about 300 MiB on disk) into `data/models/clip-b32-multilingual/`.
  It is **not** downloaded by itself: press *Descargar modelo* in Ajustes or call
  `POST /api/visual/download`. A changed model id re-downloads and re-indexes.
- **No new dependency**: it runs on the `onnxruntime`, `numpy`, `Pillow` and `httpx`
  Argus already has. The WordPiece tokenizer and the projection head are
  implemented in `argus/visual_model.py`.
- **CPU only**. The engine sets `CUDA_VISIBLE_DEVICES=-1` before loading
  onnxruntime and asks for the CPU provider, with one intra-op thread
  (`ARGUS_VISUAL_THREADS`). It never touches a GPU.
- **Only the frames Argus stores** are embedded, never the live screen. A
  background thread at the lowest OS priority takes the newest missing frames in
  batches of 4, sleeps as long as it worked (`ARGUS_VISUAL_DUTY=0.5`) and yields
  while the OCR queue has work. It is resumable (it asks the database which frames
  have no vector for the current model), and it unloads the model after 10 idle
  minutes (about 650 MB resident for the whole process while loaded). A frame that cannot be read is
  skipped, not retried in a loop.
- **Storage**: table `frame_vectors` in the Argus database, 512 float16 values
  (1 KB) per frame, with the model id. Deleting a frame (one by one, by range,
  by retention or by the storage cap) deletes its vector in the same
  transaction. Vectors of an older model are replaced and never mixed in a search.
- **Search**: `mode=text|visual|both` (default `both`). Visual mode embeds the
  query with the text tower and scores every vector by cosine (brute force over
  an in-memory float16 matrix). Both mode fuses that ranking with the OCR ranking
  by reciprocal rank fusion (k=60); a moment found both ways carries
  `via: ["text","visual"]`, `visual_score` and a fused `score`. A relevance floor
  keeps visual noise out of the fusion (absolute 0.20, within 0.05 of the best
  and, from 50 indexed frames, mean + 2 standard deviations). Without a usable
  index `both` answers with text only and says why; `visual` answers 409.
- **Find similar**: `GET /api/frames/{id}/similar`, the *Ver pantallas parecidas*
  button in Buscar and *Buscar parecidas* in the frame viewer. It embeds the
  frame on demand if it is not indexed yet and leaves out the frame's own moment.
- **Setting**: `visual_search` (default on; it only does something when the model
  is present). `GET /api/visual` returns the status: indexed/total, model, disk
  size, ms per frame, download progress.
- **Env vars**: `ARGUS_VISUAL=auto|fake|none` (`fake` is a deterministic colour
  embedder for tests), `ARGUS_VISUAL_THREADS`, `ARGUS_VISUAL_DUTY`.

Measured on this PC with the real model, one CPU thread, 1280x720 frames:
about 100 ms per frame to index (91 to 123 ms, the same in batches of 4), 6 ms to
embed a query, 8 to 13 ms for a whole HTTP search and about 1 ms to score 10 vectors. Brute force is linear; a 100,000-frame index is a
512-wide matrix product, expected in the tens of milliseconds, not measured here.

Honest limits. On ten synthetic screenshots (chart, pie, invoice, code, sheet,
terminal and so on) and fifteen English and Spanish queries the right screen came
first in 13 of 15. CLIP B/32 at 224 px sees layout, colour and the kind of
document, not small text: a dark terminal and dark code are easily confused, and
a spreadsheet described in Spanish ranked third (the English `spreadsheet grid`
ranked first). Scores are compressed (about 0.22 to 0.24 for unrelated screens,
0.25 to 0.30 for a match), so read the rank, not the number. Exact words on
screen are still the job of the OCR search; that is why `both` is the default.
The image is letterboxed (long side 224 px, grey padding), which ranked better
than squashing or centre-cropping, and the fp16-weights vision model ranks as
the 335 MB fp32 file while an int8 one halves the size and ranks clearly worse.

## The UI (Spanish)

- **Línea de tiempo**: day picker, the day grouped into *sessions* (one app +
  window seen continuously: time range, duration, count, preview thumbnails);
  a session expands into its frames with a scrubber; a frame opens as a big
  image with the OCR blocks overlaid as selectable text, prev/next (arrow keys).
- **Buscar**: query + how to search (text and look, text only, look only) + date range + app, with *Ver pantallas parecidas* on every moment; one row per moment (repeated frames of
  a window collapsed, with a thumbnail strip), times as "hoy 17:32–17:41" /
  "ayer 09:10".
- **Actividad**: time by app (bars), top window titles, per-day table.
- **Ajustes**: private mode, visual search (switch, model download, indexing progress), enabled, interval, change sensitivity, monitors,
  OCR engine (with availability of each), image width, retention, storage cap,
  exclusions (add/remove/toggle + test box) and a status card (queue, disk,
  last capture, backends, errors).

A banner on every page says **Argus está mirando / en pausa / modo privado /
captura desactivada**.

## Faustus assistant panel

Every page has a floating **Faustus** button (bottom right) that opens the Faustus assistant in a side panel, with one
conversation kept across reloads. The server side comes for free from the shared Hoard Link (`install_spa` mounts the relay
and adds the launcher to the HTML); the UI tells the panel what is on screen through `window.hoardCopilot.context()`
(`client/src/copilot-context.js`). What each turn carries, beside the page route and title:

| View | Real objects sent (`active_objects`) | Unsaved input (`view.editor`) |
|---|---|---|
| Línea de tiempo | the day (`day`: frames, hidden, seconds), the expanded session (`session`, id = its first capture), the capture picked in the scrubber (`frame`) | |
| Buscar | the executed query (`search`) or the capture it was compared with (`similar_search`), its five best moments as `frame` objects | the search form when it differs from the executed search |
| Actividad | the period (`period`: total time and top apps) | |
| Ajustes | the settings (`settings`), every exclusion rule (`exclusion`) | numeric fields typed but not committed, the "add exclusion" form |
| any page | the capture open in the viewer dialog (`frame`: title, app, time, OCR state, pinned) | |

The recognised screen text is never put in that context: the assistant reads it on demand with its own tools
(`screen_frame_text`). When the assistant finishes a turn the open view reloads in place (status, day and open session,
the last search, settings and rules, the open capture); typed fields are left alone. Settings are saved one field at a
time (`PUT /api/settings` takes a partial object), so a change made by the assistant is never overwritten by the form.

Turn it off with `HOARD_COPILOT=0` in the environment (or `install_spa(app, STATIC_DIR, copilot=False)`); the manifest
declares the panel under `x-family.copilot` in `faustus-plugin.json`.

## API

All routes are bound to `127.0.0.1` and refuse other hosts/origins.

| Route | Purpose |
| --- | --- |
| `GET /api/health` | `{service, version, dataDirConfigured}` (no auth) |
| `GET /api/status` | state, queue depth, last capture, disk usage, retention, backends, `capture_scope`, monitors, `idle_since`/`idle_s` (active screen unchanged since then) |
| `GET/PUT /api/settings` | settings (PUT accepts a partial object) |
| `POST /api/pause`, `POST /api/resume`, `POST /api/private` | recording controls (`private` toggles; body `{private: bool}` sets) |
| `GET/POST /api/exclusions`, `PATCH/DELETE /api/exclusions/{id}`, `POST /api/exclusions/test` | exclusion rules |
| `GET /api/timeline?from&to&app&q&title&limit&cursor&order` | frames with duration and excerpt, cursor pagination |
| `GET /api/sessions?day` (or `from&to`) `&app` | consecutive frames of one app + window grouped into sessions (start, end, duration, count, preview thumbs) |
| `GET /api/frames/{id}` · `/image` · `/thumb` | full text + blocks + prev/next; WebP files |
| `PATCH /api/frames/{id}/pin` | pin or unpin with `{ "pinned": true/false }` |
| `GET /api/search?q&from&to&app&limit&mode` | FTS5 candidates re-ranked with BM25 (title 3 / app 2 / text 1, smoothed IDF so `rank` is always a real negative), `snippet()` with `[ ]` markers; consecutive near-identical hits of one window within 10 min collapse into one *moment* (`first_at`, `last_at`, `count`, `frame_ids` best first); `limit` counts moments; `mode=text\|visual\|both` (default `both`) adds the visual ranking fused by RRF (`via`, `visual_score`, `score`), `both` falls back to text without a usable index and `visual` answers 409 |
| `GET /api/frames/{id}/similar?limit&from&to&app&same_moment` | moments that look like this frame (it is embedded on demand); 409 if visual search is unavailable |
| `GET /api/visual`, `POST /api/visual/download`, `POST /api/visual/reindex` | visual search status (indexed/total, model, size, ms per frame, download progress), explicit model download, drop and rebuild the index |
| `GET /api/apps?from&to` | time by app + top window titles |
| `GET /api/days` | days with data (frames, hidden ticks, seconds) |
| `DELETE /api/frames?from&to` | delete a range (permanent) |
| `GET /api/agent/tools`, `POST /api/agent/call` | tool catalog and the MCP bridge (Bearer token) |
| `GET /api/copilot/info` | the panel's identity: app id and name, data space id, panel URL and the assistant's settings URL; 503 while the assistant service cannot be reached (`HOARD_COPILOT=0` leaves all four routes out) |
| `GET /api/copilot/panel.js` | the panel's script, served through the app so the page stays same-origin |
| `/api/copilot/proxy` | relay to the assistant service (the service token stays on the server; the app identity is forced) |
| `GET /api/copilot/launcher.js` | the floating button and side panel, added to every HTML page |

`from`/`to` accept ISO datetimes, `YYYY-MM-DD` (whole day) and phrases:
`hoy`, `ayer`, `anteayer`, `esta mañana`, `esta tarde`, `anoche`, `hace 2 horas`,
`hace 15 minutos`, `últimos 30 minutos`, `esta semana`, `la semana pasada`,
`ayer a las 9`, and the English equivalents (`today`, `yesterday`, `2 hours ago`,
`this morning`, `last week`, `today at 3pm`).

## MCP tools

Existing screenshots can be added from **Importar capturas**, by selecting images or supplying file/folder paths,
and through `screen_import`. PNG, JPEG, still WebP and BMP use the ordinary local OCR and search library.
Original files remain unchanged, repeated path + SHA-256 imports reuse the stored frame, and changed contents
create a new frame. Imports preserve full image dimensions and are pinned against automatic cleanup.
The displayed date records its basis (file modification time, an explicitly supplied ISO date, or upload time).
Imports have `origin=import`; they do not add observed application time, recent screen activity or recorded
sessions. `screen_import_list` pages by frame ID, including equal timestamps; `screen_frame_text` reads their OCR.
One-time folder imports are explicit, with optional recursion. For continuous import of new or modified screenshots, use Automatic folders below.

The bridge (`mcp_server.py`) fetches the tool list from the running app and
proxies every call to `POST /api/agent/call` with the token from
`data/mcp-token`; it never opens the database.

| Tool | What it does |
| --- | --- |
| `screen_status` | recording state, queue, last capture, disk, retention |
| `screen_search` | full-text search with snippets, plus `mode` text, visual or both to find screens by how they look; each hit is a moment (`first_at`, `last_at`, `count`, `frame_ids`, `via`) |
| `screen_similar` | moments that look like a given frame |
| `screen_timeline` | what was on screen when, with durations |
| `screen_frame_text` | full OCR text of a frame (optionally blocks) |
| `screen_pin_frame` | pin or unpin a capture to preserve it through automatic cleanup |
| `screen_recent` | the last N minutes' text, deduplicated, most recent first |
| `screen_activity` | time by app + top windows + longest sessions + one-line summary |
| `screen_days` | days that have data |
| `screen_pause` / `screen_resume` | only when the user asks |
| `screen_delete_range` | permanent deletion of a range (destructive) |
| `screen_import` | import existing image files/folders, report duplicates and per-file errors |
| `screen_import_list` | list imported frames, their source, OCR state and next page |
| `screen_import_watch` | select folders for continuous import, include subfolders or check now; an empty list stops observation |
| `screen_import_watch_status` | selected folders and latest check, including files waiting for stability and partial errors |

### Automatically import screenshot folders

In **Import screenshots → Automatic folders**, save one folder per line and optionally include subfolders. New or modified PNG, JPEG, still WebP and BMP files enter the same OCR/search library when their modification time and size stay unchanged across two checks, normally five seconds apart. Repeated source/SHA pairs reuse the retained frame. Folder settings persist across restarts; missing folders retry and disappearing files do not remove their imported history. Private mode pauses observation. Save an empty folder list to stop it.

`screen_import_watch` and `screen_import_watch_status` are native API/MCP tools (16 total). `GET/POST /api/imports/watch` drives the ordinary page as well. The latest-check counters describe that check, not lifetime totals. Polling stability does not guarantee an atomic snapshot of a file being rewritten between checks; actual imported bytes retain their own SHA. The app's own data folder remains excluded by the existing import rule. No external screenshot indexer or application is required.

Connect it from Faustus with `faustus-plugin.json`, or by hand:
`{PYTHON} mcp_server.py` with env `ARGUS_URL=http://127.0.0.1:5183` and
`ARGUS_TOKEN_FILE=<repo>/data/mcp-token`.

## Tests

```bat
venv\Scripts\python -m pytest -q
```

Covers change detection, exclusions, the time-phrase resolver, real OCR on
rendered fixtures, storage/FTS/snippets, timeline durations, retention and
storage cap, the API through `TestClient` with the fake backend, agent auth,
and an end-to-end test that boots `python -m argus` in a subprocess and lists
the tools through the MCP stdio bridge.

`tests/test_visual.py` covers the visual search with a deterministic fake
embedder (fusion, resumable indexing, deletion, mode switch, model change, the
download over a local HTTP server, the API and the agent tools). One test uses
the real model and is marked `slow`: it skips unless the model is downloaded;
point `ARGUS_TEST_MODEL_DATA` at a data directory that has it.

## Verifying on the real machine

`scripts/selftest.py` takes one real capture, reads the active window, runs the
OCR engine and prints the text and timings, without starting the app. Pass an
engine name (`rapidocr`, `winocr`, `tesseract`) to force one, `--fake` to use
fixtures. This is the first thing to run on Windows: the Windows-only backends
(`mss` capture, `ctypes` active window, `winocr`) cannot be exercised on a
headless Linux build box.

## License

MIT — see `LICENSE`.
