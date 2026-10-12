"""The family assistant panel: relay routes, launcher injection, manifest entry and the client contract stay in place."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_copilot_info_answers_and_names_the_app(client):
    response = client.get("/api/copilot/info")
    assert response.status_code in (200, 503)  # 503 while the assistant service cannot be reached
    if response.status_code == 503:
        return
    body = response.json()
    assert body["app_id"] == "argus"
    assert body["app_name"]
    assert body["panel_url"] == "/api/copilot/panel.js"
    assert body["data_space_id"]


def test_html_carries_the_launcher_and_the_routes_exist(client):
    page = client.get("/")
    assert page.status_code == 200
    assert '<script type="module" src="/api/copilot/launcher.js">' in page.text
    launcher = client.get("/api/copilot/launcher.js")
    assert launcher.status_code == 200 and "hoardCopilot" in launcher.text
    panel = client.get("/api/copilot/panel.js")
    # the script comes from the assistant service: served when it is up, a clean 5xx (never a 404) when it is not
    assert panel.status_code in (200, 502, 503)
    if panel.status_code == 200:
        assert "javascript" in panel.headers["content-type"]


def test_deep_links_also_get_the_launcher(client):
    page = client.get("/linea")
    assert page.status_code == 200 and "/api/copilot/launcher.js" in page.text


def test_manifest_declares_the_copilot_contract():
    manifest = json.loads((ROOT / "faustus-plugin.json").read_text(encoding="utf-8"))
    copilot = manifest["x-family"]["copilot"]
    assert copilot["provider"] == "faustus" and copilot["contract"] == "1.0"
    assert copilot["panel"] == "/api/copilot/panel.js"
    sent = set(copilot["context"])
    assert {"frame", "session", "search", "day", "period", "settings", "exclusion", "editor"} <= sent


def test_client_registers_the_contract_once_from_the_entry():
    main = (ROOT / "client" / "src" / "main.jsx").read_text(encoding="utf-8")
    assert "installCopilot()" in main
    module = (ROOT / "client" / "src" / "copilot-context.js").read_text(encoding="utf-8")
    assert re.search(r"hoardCopilot\s*=\s*\{\s*context,\s*onTurnEnd\s*\}", module)
    assert "hoard:copilot-turn-end" in module


def test_docs_list_the_copilot_routes():
    for name in ("README.md", "README.es.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "/api/copilot/info" in text and "HOARD_COPILOT=0" in text, name
        for route in ("/api/copilot/panel.js", "/api/copilot/proxy", "/api/copilot/launcher.js", "window.hoardCopilot.context()"):
            assert route in text, (name, route)
