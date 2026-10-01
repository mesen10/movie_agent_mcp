"""
Add / remove / update the movie-agent MCP server registration in Claude Desktop
and Open WebUI.

Claude Desktop: edits the mcpServers entry in
  ~/Library/Application Support/Claude/claude_desktop_config.json

Open WebUI: calls its admin config API (GET/POST /api/v1/configs/tool_servers)
to add/remove this server as an OpenAPI tool server. Requires an Open WebUI
admin API key (Settings -> Account -> API Keys) via --openwebui-token or the
OPENWEBUI_API_KEY env var.

Usage:
    python setup_clients.py                              # add to both (default action)
    python setup_clients.py remove                       # remove from both
    python setup_clients.py status                       # status for both
    python setup_clients.py add --skip-openwebui          # Claude Desktop only
    python setup_clients.py add --skip-claude             # Open WebUI only
    python setup_clients.py add --openwebui-token sk-xxxx
"""
import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON_BIN = os.path.join(REPO_ROOT, ".venv", "bin", "python")
SERVER_SCRIPT = os.path.join(REPO_ROOT, "unified_server.py")
LOCAL_ENV_PATH = os.path.join(REPO_ROOT, "local.env")


def _load_local_env():
    if not os.path.exists(LOCAL_ENV_PATH):
        return
    with open(LOCAL_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_local_env()

CLAUDE_CONFIG_PATH = os.path.expanduser(
    "~/Library/Application Support/Claude/claude_desktop_config.json"
)
MCP_SERVER_NAME = "movie-agent"

DEFAULT_OPENWEBUI_URL = "http://localhost:3000"
TOOL_SERVER_URL = "http://host.docker.internal:8000"
TOOL_SERVER_NAME = "Movie Agent"


# ---------- Claude Desktop ----------

def _load_claude_config():
    if not os.path.exists(CLAUDE_CONFIG_PATH):
        return {}
    with open(CLAUDE_CONFIG_PATH) as f:
        return json.load(f)


def _save_claude_config(config):
    if os.path.exists(CLAUDE_CONFIG_PATH):
        shutil.copy(CLAUDE_CONFIG_PATH, CLAUDE_CONFIG_PATH + ".bak")
    os.makedirs(os.path.dirname(CLAUDE_CONFIG_PATH), exist_ok=True)
    with open(CLAUDE_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def claude_add():
    if not os.path.exists(PYTHON_BIN):
        print(f"error: venv python not found at {PYTHON_BIN}. Run `python -m venv .venv` first.")
        sys.exit(1)
    if not os.path.exists(SERVER_SCRIPT):
        print(f"error: server script not found at {SERVER_SCRIPT}")
        sys.exit(1)

    config = _load_claude_config()
    config.setdefault("mcpServers", {})
    config["mcpServers"][MCP_SERVER_NAME] = {
        "command": PYTHON_BIN,
        "args": [SERVER_SCRIPT, "--stdio"],
    }
    _save_claude_config(config)
    print(f"Claude Desktop: registered '{MCP_SERVER_NAME}' in {CLAUDE_CONFIG_PATH}")
    print("Restart Claude Desktop to load it.")


def claude_remove():
    config = _load_claude_config()
    removed = config.get("mcpServers", {}).pop(MCP_SERVER_NAME, None)
    if removed is None:
        print(f"Claude Desktop: '{MCP_SERVER_NAME}' not registered, nothing to do.")
        return
    _save_claude_config(config)
    print(f"Claude Desktop: removed '{MCP_SERVER_NAME}' from {CLAUDE_CONFIG_PATH}")
    print("Restart Claude Desktop for the change to take effect.")


def claude_status():
    config = _load_claude_config()
    entry = config.get("mcpServers", {}).get(MCP_SERVER_NAME)
    if entry is None:
        print(f"Claude Desktop: '{MCP_SERVER_NAME}' NOT registered")
    else:
        print(f"Claude Desktop: '{MCP_SERVER_NAME}' registered -> {entry}")


# ---------- Open WebUI ----------

def _api(base_url, path, token, method="GET", body=None):
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        print(f"error: Open WebUI API {method} {path} -> {e.code}: {detail}")
        sys.exit(1)


def _get_openwebui_connections(base_url, token):
    current = _api(base_url, "/api/v1/configs/tool_servers", token)
    return current.get("TOOL_SERVER_CONNECTIONS") or []


def _set_openwebui_connections(base_url, token, connections):
    _api(
        base_url,
        "/api/v1/configs/tool_servers",
        token,
        method="POST",
        body={"TOOL_SERVER_CONNECTIONS": connections},
    )


def openwebui_add(base_url, token):
    connections = _get_openwebui_connections(base_url, token)
    connections = [c for c in connections if c.get("url") != TOOL_SERVER_URL]
    connections.append(
        {
            "url": TOOL_SERVER_URL,
            "path": "/openapi.json",
            "type": "openapi",
            "auth_type": "none",
            "headers": None,
            "key": None,
            "config": {"enable": True},
            "info": {"name": TOOL_SERVER_NAME},
        }
    )
    _set_openwebui_connections(base_url, token, connections)
    print(f"Open WebUI: registered '{TOOL_SERVER_NAME}' ({TOOL_SERVER_URL}) at {base_url}")
    print("Enable it per-model under Select Model -> Tools.")


def openwebui_remove(base_url, token):
    connections = _get_openwebui_connections(base_url, token)
    kept = [c for c in connections if c.get("url") != TOOL_SERVER_URL]
    if len(kept) == len(connections):
        print(f"Open WebUI: '{TOOL_SERVER_NAME}' not registered at {base_url}, nothing to do.")
        return
    _set_openwebui_connections(base_url, token, kept)
    print(f"Open WebUI: removed '{TOOL_SERVER_NAME}' ({TOOL_SERVER_URL}) from {base_url}")


def openwebui_status(base_url, token):
    connections = _get_openwebui_connections(base_url, token)
    match = next((c for c in connections if c.get("url") == TOOL_SERVER_URL), None)
    if match is None:
        print(f"Open WebUI: '{TOOL_SERVER_NAME}' NOT registered at {base_url}")
    else:
        print(f"Open WebUI: '{TOOL_SERVER_NAME}' registered at {base_url} -> {match}")


# ---------- CLI ----------

def _get_openwebui_token(args):
    token = args.openwebui_token
    if not token:
        token = input("Open WebUI admin API key (Settings -> Account -> API Keys): ").strip()
    if not token:
        print("error: Open WebUI API key required")
        sys.exit(1)
    return token


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["add", "remove", "status"], nargs="?", default="add")
    parser.add_argument("--skip-claude", action="store_true", help="skip Claude Desktop")
    parser.add_argument("--skip-openwebui", action="store_true", help="skip Open WebUI")
    parser.add_argument("--openwebui-url", default=DEFAULT_OPENWEBUI_URL, help=f"Open WebUI base URL (default {DEFAULT_OPENWEBUI_URL})")
    parser.add_argument("--openwebui-token", default=os.environ.get("OPENWEBUI_API_KEY"), help="Open WebUI admin API key (or set OPENWEBUI_API_KEY / local.env)")
    args = parser.parse_args()

    if not args.skip_claude:
        {"add": claude_add, "remove": claude_remove, "status": claude_status}[args.action]()

    if not args.skip_openwebui:
        token = _get_openwebui_token(args)
        fn = {"add": openwebui_add, "remove": openwebui_remove, "status": openwebui_status}[args.action]
        fn(args.openwebui_url, token)


if __name__ == "__main__":
    main()
