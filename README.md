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
- **Delete range**: `DELETE /api/frames?from&to`, "Borrar este día" in the
  timeline, or the `screen_delete_range` tool. Permanent.

## Requirements

- Windows 10/11 (capture + active window). The whole pipeline after capture
  also runs on Linux/macOS with the fake backend for tests and demos.
- Python 3.11+ (3.13 works). Node 22 only to build the client.
- CPU is enough. With `ocr_backend: auto` the engine is `winocr`
  (Windows.Media.Ocr, about 150 ms per 1080p frame, needs
  `requirements-windows.txt`) when it is available and `rapidocr` (ONNX on
  CPU, cross-platform) otherwise; `tesseract` is used if `pytesseract` and the
  binary are installed. Any of the three can be forced in Ajustes.

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
`ARGUS_AUTOSTART=0` (do not start the recorder thread).

### Access from your phone (behind a tunnel)

The server binds 127.0.0.1 and only answers requests whose `Host` is `localhost`, `127.0.0.1` or `[::1]`. To reach it from your phone through a tunnel that fronts the app (a private mesh network, a reverse proxy), list the extra host names in `ARGUS_ALLOWED_HOSTS`, comma-separated, exact names or `*.suffix`: `ARGUS_ALLOWED_HOSTS=my-pc.example,*.ts.net`. Port and letter case are ignored, and the `Origin` of API calls must resolve to one of those hosts too (any scheme or port). Cross-site *fetches* are still refused; opening the app from another page (a link, a bookmarklet, the share sheet) is a normal navigation and works.

Development: `python scripts/dev.py` runs uvicorn `--reload` plus the Vite dev
server (proxying `/api`).

## The UI (Spanish)

- **Línea de tiempo**: day picker, the day grouped into *sessions* (one app +
  window seen continuously: time range, duration, count, preview thumbnails);
  a session expands into its frames with a scrubber; a frame opens as a big
  image with the OCR blocks overlaid as selectable text, prev/next (arrow keys).
- **Buscar**: query + date range + app; one row per moment (repeated frames of
  a window collapsed, with a thumbnail strip), times as "hoy 17:32–17:41" /
  "ayer 09:10".
- **Actividad**: time by app (bars), top window titles, per-day table.
- **Ajustes**: private mode, enabled, interval, change sensitivity, monitors,
  OCR engine (with availability of each), image width, retention, storage cap,
  exclusions (add/remove/toggle + test box) and a status card (queue, disk,
  last capture, backends, errors).

A banner on every page says **Argus está mirando / en pausa / modo privado /
captura desactivada**.

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
| `GET /api/search?q&from&to&app&limit` | FTS5 candidates re-ranked with BM25 (title 3 / app 2 / text 1, smoothed IDF so `rank` is always a real negative), `snippet()` with `[ ]` markers; consecutive near-identical hits of one window within 10 min collapse into one *moment* (`first_at`, `last_at`, `count`, `frame_ids` best first); `limit` counts moments |
| `GET /api/apps?from&to` | time by app + top window titles |
| `GET /api/days` | days with data (frames, hidden ticks, seconds) |
| `DELETE /api/frames?from&to` | delete a range (permanent) |
| `GET /api/agent/tools`, `POST /api/agent/call` | tool catalog and the MCP bridge (Bearer token) |

`from`/`to` accept ISO datetimes, `YYYY-MM-DD` (whole day) and phrases:
`hoy`, `ayer`, `anteayer`, `esta mañana`, `esta tarde`, `anoche`, `hace 2 horas`,
`hace 15 minutos`, `últimos 30 minutos`, `esta semana`, `la semana pasada`,
`ayer a las 9`, and the English equivalents (`today`, `yesterday`, `2 hours ago`,
`this morning`, `last week`, `today at 3pm`).

## MCP tools

The bridge (`mcp_server.py`) fetches the tool list from the running app and
proxies every call to `POST /api/agent/call` with the token from
`data/mcp-token`; it never opens the database.

| Tool | What it does |
| --- | --- |
| `screen_status` | recording state, queue, last capture, disk, retention |
| `screen_search` | full-text search with snippets; each hit is a moment (`first_at`, `last_at`, `count`, `frame_ids`) |
| `screen_timeline` | what was on screen when, with durations |
| `screen_frame_text` | full OCR text of a frame (optionally blocks) |
| `screen_recent` | the last N minutes' text, deduplicated, most recent first |
| `screen_activity` | time by app + top windows + longest sessions + one-line summary |
| `screen_days` | days that have data |
| `screen_pause` / `screen_resume` | only when the user asks |
| `screen_delete_range` | permanent deletion of a range (destructive) |

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

## Verifying on the real machine

`scripts/selftest.py` takes one real capture, reads the active window, runs the
OCR engine and prints the text and timings, without starting the app. Pass an
engine name (`rapidocr`, `winocr`, `tesseract`) to force one, `--fake` to use
fixtures. This is the first thing to run on Windows: the Windows-only backends
(`mss` capture, `ctypes` active window, `winocr`) cannot be exercised on a
headless Linux build box.

## License

MIT — see `LICENSE`.
