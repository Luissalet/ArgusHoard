import time

from conftest import ticks, wait_ocr


def test_health_and_status(client):
    health = client.get("/api/health").json()
    assert health["service"] == "argus-hoard" and health["dataDirConfigured"] is True
    status = client.get("/api/status").json()
    assert status["state"] == "watching" and status["capture_backend"] == "fake"
    assert status["queue_depth"] == 0 and status["frames_total"] == 0


def test_rejects_non_local_hosts(client):
    response = client.get("/api/health", headers={"host": "evil.example"})
    assert response.status_code == 403 and "error" in response.json()
    response = client.get("/api/status", headers={"origin": "http://evil.example"})
    assert response.status_code == 403


def test_settings_and_controls(client):
    assert client.get("/api/settings").json()["interval_s"] == 5
    updated = client.put("/api/settings", json={"interval_s": 10, "retention_days": 7}).json()
    assert updated["interval_s"] == 10 and updated["retention_days"] == 7
    assert client.put("/api/settings", json={"interval_s": 0}).status_code == 400
    assert client.put("/api/settings", json={"ocr_backend": "magic"}).status_code == 400

    assert client.post("/api/pause").json()["state"] == "paused"
    assert client.get("/api/status").json()["paused"] is True
    assert client.post("/api/private").json()["private"] is True
    assert client.get("/api/status").json()["state"] == "private"
    assert client.post("/api/private", json={"private": False}).json()["private"] is False
    assert client.get("/api/status").json()["state"] == "paused"
    assert client.post("/api/resume").json()["state"] == "watching"
    client.put("/api/settings", json={"enabled": False})
    assert client.get("/api/status").json()["state"] == "disabled"


def test_exclusions_crud_and_test_box(client):
    created = client.post("/api/exclusions", json={"kind": "app", "pattern": "keepass*"})
    assert created.status_code == 201
    again = client.post("/api/exclusions", json={"kind": "app", "pattern": "keepass*"}).json()
    assert again["id"] == created.json()["id"]  # idempotent on (kind, pattern)
    assert client.post("/api/exclusions", json={"kind": "title", "pattern": "[bad"}).status_code == 400
    title_rule = client.post("/api/exclusions", json={"kind": "title", "pattern": "inc[oó]gnito"}).json()
    assert len(client.get("/api/exclusions").json()["exclusions"]) == 2

    check = client.post("/api/exclusions/test", json={"app": "KeePassXC.exe", "title": "Base de datos"}).json()
    assert check["excluded"] and check["rule"]["kind"] == "app"
    check = client.post("/api/exclusions/test", json={"app": "chrome", "title": "Ventana de incógnito"}).json()
    assert check["excluded"] and check["rule"]["id"] == title_rule["id"]
    assert client.patch(f"/api/exclusions/{title_rule['id']}", json={"enabled": False}).json()["ok"]
    assert not client.post("/api/exclusions/test", json={"app": "chrome", "title": "Ventana de incógnito"}).json()["excluded"]
    assert client.delete(f"/api/exclusions/{title_rule['id']}").json()["ok"]
    assert client.delete(f"/api/exclusions/{title_rule['id']}").status_code == 404
    assert len(client.get("/api/exclusions").json()["exclusions"]) == 1


def test_timeline_frames_search_apps_days(client):
    svc = client.services
    stored = ticks(svc, 8, start=time.time() - 120)
    wait_ocr(svc, stored)

    timeline = client.get("/api/timeline", params={"from": "hoy", "limit": 2}).json()
    assert len(timeline["frames"]) == 2 and timeline["next_cursor"] is not None
    assert timeline["frames"][0]["excerpt"]
    page2 = client.get("/api/timeline", params={"from": "hoy", "limit": 2, "cursor": timeline["next_cursor"]}).json()
    assert page2["frames"] and page2["frames"][0]["id"] not in {f["id"] for f in timeline["frames"]}
    assert client.get("/api/timeline", params={"from": "el año que viene"}).status_code == 400
    by_app = client.get("/api/timeline", params={"app": "terminal"}).json()["frames"]
    assert by_app and all(f["app"] == "terminal" for f in by_app)
    filtered = client.get("/api/timeline", params={"q": "paella"}).json()["frames"]
    assert len(filtered) == 1 and filtered[0]["app"] == "navegador"

    frame = client.get(f"/api/frames/{stored[0]}").json()
    assert frame["blocks"] and "compra" in frame["text"].lower()
    assert frame["prev"] is None and frame["next"] == stored[1]
    assert client.get("/api/frames/999999").status_code == 404
    image = client.get(f"/api/frames/{stored[0]}/image")
    assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
    thumb = client.get(f"/api/frames/{stored[0]}/thumb")
    assert thumb.status_code == 200 and len(thumb.content) < len(image.content)

    search = client.get("/api/search", params={"q": "keyerror"}).json()
    assert len(search["hits"]) == 1 and "[KeyError" in search["hits"][0]["snippet"]
    assert client.get("/api/search", params={"q": ""}).status_code == 400

    apps = client.get("/api/apps", params={"from": "hoy"}).json()
    assert apps["total_seconds"] == 40 and apps["apps"][0]["app"] == "editor"
    days = client.get("/api/days").json()["days"]
    assert len(days) == 1 and days[0]["frames"] == len(stored)


def test_delete_range(client):
    svc = client.services
    start = time.time() - 600
    stored = ticks(svc, 6, start=start)
    assert len(stored) == 3
    middle = svc.queries.frame(stored[1])
    response = client.delete("/api/frames", params={"from": middle["captured_at"], "to": middle["until_at"]})
    assert response.json()["deleted"] == 1
    assert client.get(f"/api/frames/{stored[1]}").status_code == 404
    assert client.get(f"/api/frames/{stored[0]}").status_code == 200
    assert client.delete("/api/frames", params={"from": "hoy"}).status_code == 400  # `to` is required


def test_agent_tools_and_call_auth(client):
    catalog = client.get("/api/agent/tools").json()
    names = [t["name"] for t in catalog["tools"]]
    assert names == [
        "screen_status", "screen_search", "screen_timeline", "screen_frame_text", "screen_recent",
        "screen_activity", "screen_days", "screen_pause", "screen_resume", "screen_delete_range",
    ]
    assert all("Sinónimos:" in t["description"] for t in catalog["tools"])
    assert catalog["tools"][1]["inputSchema"]["properties"]["from"]
    assert catalog["tools"][-1]["annotations"]["destructiveHint"] is True
    assert "screen_recent" in catalog["instructions"]

    token = client.services.token
    assert client.post("/api/agent/call", json={"name": "screen_status"}).status_code == 401
    assert client.post("/api/agent/call", json={"name": "screen_status"}, headers={"Authorization": "Bearer nope"}).status_code == 401
    auth = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/agent/call", json={"name": "screen_status"}, headers=auth).json()["state"] == "watching"
    assert client.post("/api/agent/call", json={"name": "nope"}, headers=auth).status_code == 404
    bad = client.post("/api/agent/call", json={"name": "screen_search", "arguments": {}}, headers=auth)
    assert bad.status_code == 400 and "q" in bad.json()["error"]
    bad_time = client.post("/api/agent/call", json={"name": "screen_search", "arguments": {"q": "x", "from": "nunca"}}, headers=auth)
    assert bad_time.status_code == 400

    stored = ticks(client.services, 3, start=time.time() - 60)
    wait_ocr(client.services, stored)
    recent = client.post("/api/agent/call", json={"name": "screen_recent", "arguments": {"minutes": 5}}, headers=auth).json()
    assert recent["count"] == 1 and "compra" in recent["frames"][0]["text"].lower()
    hits = client.post("/api/agent/call", json={"name": "screen_search", "arguments": {"q": "fontanero", "from": "hace 1 hora"}}, headers=auth).json()
    assert hits["count"] == 1 and hits["resolved"]["from"]
    activity = client.post("/api/agent/call", json={"name": "screen_activity", "arguments": {"from": "hoy"}}, headers=auth).json()
    assert "editor" in activity["summary"]
    paused = client.post("/api/agent/call", json={"name": "screen_pause"}, headers=auth).json()
    assert paused["state"] == "paused"
    missing = client.post("/api/agent/call", json={"name": "screen_frame_text", "arguments": {"id": 4242}}, headers=auth)
    assert missing.status_code == 404
