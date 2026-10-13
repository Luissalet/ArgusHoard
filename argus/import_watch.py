"""Observe selected screenshot folders using the existing import/OCR library."""
from __future__ import annotations

import os
from pathlib import Path
import threading
import time

from pydantic import BaseModel, Field

from .imports import EXTENSIONS, ScreenImportArgs, import_paths


class ImportWatchArgs(BaseModel):
    folders: list[str] | None = Field(None, description="Replace selected folders; [] stops watching. Originals remain untouched.")
    recursive: bool | None = Field(None, description="Include subfolders.")
    scan: bool = Field(False, description="Check now in addition to the background observer. Files must be unchanged over two observations.")


class ImportWatch:
    interval_s = 5

    def __init__(self, services):
        self.services = services
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._seen = {}
        self._imported = {}
        self._last = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="argus-import-watch", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def wake(self):
        self._wake.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.scan()
            except Exception as exc:
                with self._lock:
                    self._last = {"checked_at": time.time(), "errors": [{"source": "observer", "error": str(exc)}]}
            self._wake.wait(self.interval_s)
            self._wake.clear()

    def status(self):
        with self._lock:
            settings = self.services.settings.get()
            return {"folders": list(settings.import_watch_folders), "recursive": settings.import_watch_recursive,
                    "state": "private" if settings.private else "watching" if settings.import_watch_folders else "disabled",
                    "interval_s": self.interval_s, "last_scan": self._last}

    def configure(self, args: ImportWatchArgs):
        patch = {}
        if args.folders is not None:
            patch["import_watch_folders"] = list(dict.fromkeys(str(Path(p.strip()).expanduser().resolve()) for p in args.folders if p.strip()))
        if args.recursive is not None:
            patch["import_watch_recursive"] = args.recursive
        if patch:
            self.services.update_settings(patch)
        if args.scan:
            self.scan()
        return self.status()

    def scan(self):
        # A manual scan and the background scan must not race over observation state.
        with self._lock:
            settings = self.services.settings.get()
            spec = (tuple(settings.import_watch_folders), settings.import_watch_recursive)
            result = {"checked_at": time.time(), "imported": 0, "duplicates": 0, "waiting": 0, "errors": []}
            if settings.private or not spec[0]:
                self._last = result
                return result
            own_data = self.services.config.data_dir.resolve()
            paths = {}
            for raw in spec[0]:
                try:
                    folder = Path(raw).expanduser().resolve()
                    if folder.is_relative_to(own_data):
                        raise ValueError("Choose original screenshots outside the application's own data folder.")
                    if not folder.is_dir():
                        raise ValueError("Folder not found; it will be checked again.")
                    for path in folder.rglob("*") if spec[1] else folder.iterdir():
                        if path.suffix.lower() in EXTENSIONS and path.is_file():
                            resolved = path.resolve()
                            if not resolved.is_relative_to(own_data):
                                paths[os.path.normcase(str(resolved))] = resolved
                except (OSError, ValueError) as exc:
                    result["errors"].append({"source": raw, "error": str(exc)})
            for source, path in paths.items():
                current = self.services.settings.get()
                if self._stop.is_set() or current.private or (tuple(current.import_watch_folders), current.import_watch_recursive) != spec:
                    result["interrupted"] = True
                    break
                try:
                    stat = path.stat()
                    signature = (stat.st_mtime_ns, stat.st_size)
                    if self._seen.get(source) != signature:
                        self._seen[source] = signature
                        result["waiting"] += 1
                        continue
                    if self._imported.get(source) == signature:
                        continue
                    imported = import_paths(self.services, ScreenImportArgs(paths=[str(path)]))
                    result["imported"] += imported["imported"]
                    result["duplicates"] += imported["duplicates"]
                    result["errors"].extend(imported["errors"])
                    # A file may change between observation and import; do not mark that new version as handled.
                    after = path.stat()
                    if not imported["errors"] and (after.st_mtime_ns, after.st_size) == signature:
                        self._imported[source] = signature
                except OSError as exc:
                    result["errors"].append({"source": source, "error": str(exc)})
            # Disappearing files leave the retained library intact and can be re-observed later.
            self._seen = {key: value for key, value in self._seen.items() if key in paths}
            self._imported = {key: value for key, value in self._imported.items() if key in paths}
            self._last = result
            return result
