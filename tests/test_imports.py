from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import os
from pathlib import Path
import time

from PIL import Image, ImageDraw, ImageFont
import pytest

from argus.imports import ScreenImportArgs, import_paths, import_image


def image_bytes(text="ARCHIVO LIMA FACTURA 1250", width=720):
    image = Image.new("RGB", (width, 300), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 32) if Path("C:/Windows/Fonts/arial.ttf").exists() else ImageFont.load_default(size=32)
    draw.text((30, 40), text, fill="black", font=font)
    stream = BytesIO(); image.save(stream, "PNG")
    return stream.getvalue()


def test_files_are_idempotent_preserved_and_not_observed_activity(services, tmp_path):
    path = tmp_path/"factura.png"
    path.write_bytes(image_bytes())
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    at = time.time()-86400*400
    os.utime(path,(at,at))
    args = ScreenImportArgs(paths=[str(path)])
    first = import_paths(services,args)
    repeat = import_paths(services,args)
    assert first["imported"]==1 and repeat["duplicates"]==1
    assert first["frames"][0]["id"]==repeat["frames"][0]["id"]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==original
    frame = services.queries.frame(first["frames"][0]["id"])
    assert frame["origin"]=="import" and frame["time_basis"]=="file_mtime" and frame["pinned"]
    assert frame["duration_s"]==0
    assert services.queries.apps(None,None)["total_seconds"]==0
    assert services.queries.apps(None,None)["apps"]==[]
    assert services.queries.sessions()==[]
    assert services.queries.recent(at-1,20)==[]
    assert services.frames.last_frame(0) is None
    from argus.agent_tools import TimelineArgs, run_timeline
    for group in (True, False):
        assert run_timeline(services, TimelineArgs(**{"from":"2020-01-01", "to":"2030-01-01", "group":group}))["count"] == 0
    services.janitor.run()
    assert services.queries.frame(frame["id"]) is not None


def test_partial_errors_and_changed_source_keep_previous_frame(services,tmp_path):
    a=tmp_path/"a.png";b=tmp_path/"bad.png";c=tmp_path/"missing.png"
    a.write_bytes(image_bytes());b.write_bytes(b"not an image")
    result=import_paths(services,ScreenImportArgs(paths=[str(a),str(b),str(c)]))
    assert result["imported"]==1 and len(result["errors"])==2
    a.write_bytes(image_bytes("ARCHIVO AZUL FACTURA 2000"))
    revised=import_paths(services,ScreenImportArgs(paths=[str(a)]))
    assert revised["imported"]==1 and revised["frames"][0]["id"]!=result["frames"][0]["id"]
    assert services.frames.frame_count()==2


def test_concurrent_imports_have_one_frame(services,tmp_path):
    path=tmp_path/"same.png";path.write_bytes(image_bytes())
    args=ScreenImportArgs(paths=[str(path)])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:import_paths(services,args),range(2)))
    assert sum(r["imported"] for r in results)==1
    assert sum(r["duplicates"] for r in results)==1
    assert services.frames.frame_count()==1


def test_folder_recursion_and_equal_timestamp_pagination(services,tmp_path):
    folder=tmp_path/"archive";folder.mkdir();nested=folder/"nested";nested.mkdir()
    for index,root in enumerate([folder,folder,nested]):
        (root/f"image{index}.png").write_bytes(image_bytes(str(index)))
    a=import_paths(services,ScreenImportArgs(paths=[str(folder)],captured_at="2025-10-01"))
    assert a["imported"]==2
    b=import_paths(services,ScreenImportArgs(paths=[str(folder)],recursive=True,captured_at="2025-10-01"))
    assert b["imported"]==1 and b["duplicates"]==2
    first=services.queries.imported(limit=2)
    second=services.queries.imported(limit=2,before=first["next_before"])
    assert len(first["frames"])+len(second["frames"])==3
    assert len({f["id"] for f in first["frames"]+second["frames"]})==3


def test_high_resolution_source_and_uploaded_duplicates(client,tmp_path):
    raw=image_bytes(width=2400)
    one=client.post("/api/imports/upload",files={"files":("public.png",raw,"image/png")},data={"modified":"[1700000000]"})
    assert one.status_code==200,one.text
    frame_id=one.json()["frames"][0]["id"]
    frame=client.get(f"/api/frames/{frame_id}").json()
    assert frame["width"]==2400 and frame["origin"]=="import"
    picture=client.get(f"/api/frames/{frame_id}/image")
    assert Image.open(BytesIO(picture.content)).width==2400
    repeat=client.post("/api/imports/upload",files={"files":("public.png",raw,"image/png")})
    assert repeat.json()["duplicates"]==1
    assert client.get("/api/imports").json()["frames"][0]["source_sha256"]==hashlib.sha256(raw).hexdigest()


def test_real_store_failure_does_not_leave_row_or_image(services,tmp_path,monkeypatch):
    path=tmp_path/"fail.png";path.write_bytes(image_bytes())
    from argus import images
    original=images.save_frame_images
    def fail_after_image(*args,**kwargs):
        original(*args,**kwargs)
        raise OSError("invented disk error")
    monkeypatch.setattr(images,"save_frame_images",fail_after_image)
    result=import_paths(services,ScreenImportArgs(paths=[str(path)]))
    assert result["imported"]==0 and len(result["errors"])==1
    assert services.frames.frame_count()==0
    assert list(services.config.frames_dir.rglob("*.webp"))==[]
    assert path.exists()


def test_empty_and_inaccessible_folders_keep_valid_files(services, tmp_path, monkeypatch):
    empty = tmp_path/"empty"; empty.mkdir()
    denied = tmp_path/"denied"; denied.mkdir()
    good = tmp_path/"good.png"; good.write_bytes(image_bytes())
    original = Path.iterdir
    def enumerate_folder(path):
        if path == denied:
            raise PermissionError("invented access error")
        return original(path)
    monkeypatch.setattr(Path, "iterdir", enumerate_folder)
    result = import_paths(services, ScreenImportArgs(paths=[str(empty), str(denied), str(good)]))
    assert result["imported"] == 1 and len(result["errors"]) == 2


def test_schema_upgrade_preserves_existing_capture_and_text(tmp_path):
    from argus.db import Database, MIGRATIONS
    from argus.hoard_link.sqlkit import Database as BaseDatabase
    from argus.store import FrameStore
    from argus.hoard_link.docs.imaging import dhash
    path = tmp_path/"upgrade.db"
    old = BaseDatabase(path, migrations=MIGRATIONS[:3])
    image = Image.open(BytesIO(image_bytes())).convert("RGB")
    store = FrameStore(old, tmp_path/"frames")
    frame_id = store.insert_frame(image, captured_at=1700000000, interval_s=5, monitor=1,
                                  app="Existing app", window_title="Existing window", phash=dhash(image), image_max_width=720)
    old.conn.execute("INSERT INTO frames_fts(rowid,text,window_title,app) VALUES (?,?,?,?)",
                     (frame_id,"Existing OCR","Existing window","Existing app"))
    columns = [row[1] for row in old.conn.execute("PRAGMA table_info(frames)")]
    before = tuple(old.conn.execute("SELECT * FROM frames").fetchone())
    old.close()
    new = Database(path)
    assert tuple(new.conn.execute("SELECT "+",".join(columns)+" FROM frames").fetchone()) == before
    assert new.conn.execute("SELECT text FROM frames_fts WHERE rowid=?", (frame_id,)).fetchone()[0] == "Existing OCR"
    row = new.conn.execute("SELECT origin,time_basis,source_path FROM frames").fetchone()
    assert tuple(row) == ("capture", "capture", "")
    new.close()


def test_imports_and_captures_do_not_merge_into_observed_moments():
    from argus.search import Candidate, group_moments
    captured = Candidate(1, 100, "same", "same", "same text", "same text", {"origin":"capture"})
    imported = Candidate(2, 101, "same", "same", "same text", "same text", {"origin":"import"})
    assert len(group_moments([(captured,-1),(imported,-1)])) == 2
