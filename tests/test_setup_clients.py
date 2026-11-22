import json
import os

import pytest

import setup_clients as sc


@pytest.fixture
def fake_claude_config(tmp_path, monkeypatch):
    cfg = tmp_path / "claude_desktop_config.json"
    monkeypatch.setattr(sc, "CLAUDE_CONFIG_PATH", str(cfg))
    return cfg


@pytest.fixture
def venv_present(tmp_path, monkeypatch):
    py = tmp_path / "python"
    py.write_text("")
    monkeypatch.setattr(sc, "PYTHON_BIN", str(py))
    return py


def test_claude_add_registers_stdio_server(fake_claude_config, venv_present):
    sc.claude_add()
    entry = json.loads(fake_claude_config.read_text())["mcpServers"][sc.MCP_SERVER_NAME]
    assert entry == {"command": str(venv_present), "args": [sc.SERVER_SCRIPT, "--stdio"]}


def test_claude_add_keeps_other_servers_and_backs_up(fake_claude_config, venv_present):
    fake_claude_config.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    sc.claude_add()
    servers = json.loads(fake_claude_config.read_text())["mcpServers"]
    assert "other" in servers and sc.MCP_SERVER_NAME in servers
    assert os.path.exists(str(fake_claude_config) + ".bak")


def test_claude_add_fails_without_venv(fake_claude_config, monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "PYTHON_BIN", str(tmp_path / "missing"))
    with pytest.raises(SystemExit):
        sc.claude_add()
    assert not fake_claude_config.exists()


def test_claude_remove_is_idempotent(fake_claude_config, venv_present, capsys):
    sc.claude_remove()  # nothing registered yet
    assert "nothing to do" in capsys.readouterr().out
    sc.claude_add()
    sc.claude_remove()
    assert sc.MCP_SERVER_NAME not in json.loads(fake_claude_config.read_text())["mcpServers"]


def test_openwebui_add_replaces_existing_entry_instead_of_duplicating(monkeypatch):
    existing = [{"url": sc.TOOL_SERVER_URL, "info": {"name": "stale"}}, {"url": "http://other"}]
    saved = {}

    def fake_api(base_url, path, token, method="GET", body=None):
        if method == "GET":
            return {"TOOL_SERVER_CONNECTIONS": existing}
        saved["body"] = body
        return {}

    monkeypatch.setattr(sc, "_api", fake_api)
    sc.openwebui_add("http://localhost:3000", "token")

    conns = saved["body"]["TOOL_SERVER_CONNECTIONS"]
    ours = [c for c in conns if c["url"] == sc.TOOL_SERVER_URL]
    assert len(ours) == 1
    assert ours[0]["info"]["name"] == sc.TOOL_SERVER_NAME
    assert any(c["url"] == "http://other" for c in conns)
