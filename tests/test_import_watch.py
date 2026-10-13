"""Real library behavior; no screen capture, external watcher or model."""
from io import BytesIO
import time

from PIL import Image

from argus.import_watch import ImportWatchArgs
from argus.settings import SettingsStore


def picture(path, color="red"):
    image = Image.new("RGB", (120, 80), color)
    image.save(path)


def configure(svc, folders, recursive=False):
    return svc.import_watch.configure(ImportWatchArgs(folders=[str(p) for p in folders], recursive=recursive))


def test_new_changed_deleted_and_repeated_originals(services, tmp_path):
    folder = tmp_path / "screens"; folder.mkdir()
    source = folder / "one.png"; picture(source)
    configure(services, [folder])
    assert services.import_watch.scan()["waiting"] == 1
    assert services.import_watch.scan()["imported"] == 1
    original = source.read_bytes()
    assert services.import_watch.scan()["imported"] == 0
    first = services.queries.imported()["frames"][0]
    assert first["origin"] == "import" and first["pinned"]
    assert source.read_bytes() == original
    picture(source, "blue")
    assert services.import_watch.scan()["waiting"] == 1
    assert services.import_watch.scan()["imported"] == 1
    source.unlink()
    services.import_watch.scan()
    assert services.frames.frame_count() == 2
    source.write_bytes(original)
    services.import_watch.scan()
    assert services.import_watch.scan()["duplicates"] == 1
    assert services.frames.frame_count() == 2
    assert services.queries.apps(None, None)["total_seconds"] == 0


def test_changed_file_waits_and_partial_errors_recover(services, tmp_path):
    folder = tmp_path / "screens"; folder.mkdir()
    good = folder / "good.png"; picture(good)
    bad = folder / "bad.png"; bad.write_bytes(b"incomplete")
    configure(services, [folder, tmp_path / "absent"])
    services.import_watch.scan()
    picture(good, "green")
    result = services.import_watch.scan()
    assert result["waiting"] == 1 and result["imported"] == 0 and len(result["errors"]) == 2
    result = services.import_watch.scan()
    assert result["imported"] == 1
    picture(bad, "blue")
    services.import_watch.scan()
    assert services.import_watch.scan()["imported"] == 1


def test_recursion_overlap_own_data_and_private_mode(services, tmp_path):
    folder = tmp_path / "screens"; folder.mkdir(); nested = folder / "nested"; nested.mkdir()
    picture(folder / "one.png"); picture(nested / "two.png")
    configure(services, [folder])
    services.import_watch.scan()
    assert services.import_watch.scan()["imported"] == 1
    configure(services, [folder, nested, services.config.data_dir], recursive=True)
    services.update_settings({"private": True})
    assert services.import_watch.status()["state"] == "private"
    assert services.import_watch.scan()["imported"] == 0
    services.update_settings({"private": False})
    services.import_watch.scan()
    result = services.import_watch.scan()
    assert result["imported"] == 1 and len(result["errors"]) == 1
    assert services.frames.frame_count() == 2
    assert SettingsStore(services.db).get().import_watch_folders == services.settings.get().import_watch_folders
    configure(services, [])
    assert services.import_watch.status()["state"] == "disabled" and services.frames.frame_count() == 2


def test_restart_reuses_source_sha_and_actual_background_thread(services, tmp_path):
    folder = tmp_path / "screens"; folder.mkdir(); picture(folder / "one.png")
    configure(services, [folder])
    services.import_watch.interval_s = .02
    services.import_watch.start()
    deadline = time.monotonic() + 5
    while services.frames.frame_count() == 0 and time.monotonic() < deadline:
        time.sleep(.01)
    services.import_watch.stop()
    assert services.frames.frame_count() == 1 and services.import_watch._thread is None
    from argus.import_watch import ImportWatch
    reopened = ImportWatch(services)
    reopened.scan()
    assert reopened.scan()["duplicates"] == 1 and services.frames.frame_count() == 1


def test_api_tools_share_status_and_settings(client, tmp_path):
    folder = tmp_path / "screens"; folder.mkdir()
    result = client.post("/api/imports/watch", json={"folders": [str(folder)], "recursive": True})
    assert result.status_code == 200 and result.json()["folders"] == [str(folder.resolve())]
    assert client.get("/api/imports/watch").json()["recursive"] is True
    from argus.agent_tools import TOOLS
    assert {t.name for t in TOOLS} >= {"screen_import_watch", "screen_import_watch_status"}
    stopped = client.post("/api/imports/watch", json={"folders": []})
    assert stopped.json()["state"] == "disabled"
