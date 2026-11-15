#!/usr/bin/env python3
"""Publish (or update) the MCP server's entry in the official MCP registry (registry.modelcontextprotocol.io).

Usage: uv run bin/mcp_registry.py [--version 1.0.1] [--dry-run]

Domain authentication over HTTP, no personal account: the site serves /.well-known/mcp-registry-auth with the
public key (ltlaw.render.MCP_REGISTRY_PUBKEY); this script signs the current time with the private key
(~/.config/lt-law/mcp-registry-ed25519.pem, chmod 600, never printed; OpenSSL 3), exchanges it for a registry token
and publishes server.json under the namespace lt.atviri-teises-aktai. A new version is needed for every change of
the entry. Standard library + the openssl command.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import tempfile
import urllib.error
import urllib.request

REGISTRY = "https://registry.modelcontextprotocol.io"
DOMAIN = "atviri-teises-aktai.lt"
KEY = pathlib.Path.home() / ".config" / "lt-law" / "mcp-registry-ed25519.pem"


def server_json(version: str) -> dict:
    return {
        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
        "name": "lt.atviri-teises-aktai/lithuanian-law",
        "title": "Atviri teisės aktai – Lithuanian law",
        "description": "Lithuanian laws article by article, with whether each applies today, past versions and search",
        "version": version,
        "websiteUrl": f"https://{DOMAIN}/",
        # PNG first: clients must render PNG, SVG only should (schema 2025-12-11); both are the site's own files
        "icons": [{"src": f"https://{DOMAIN}/icon-512.png", "mimeType": "image/png", "sizes": ["512x512"]},
                  {"src": f"https://{DOMAIN}/favicon.svg", "mimeType": "image/svg+xml", "sizes": ["any"]}],
        "remotes": [{"type": "streamable-http", "url": f"https://{DOMAIN}/mcp"}],
        # the public code repository (D-055); id: gh api repos/marrgss/lt-law --jq .id
        "repository": {"url": "https://github.com/marrgss/lt-law", "source": "github", "id": "1458570426"},
    }


def post(path: str, body: dict, token: str | None = None) -> tuple[int, dict | str]:
    req = urllib.request.Request(REGISTRY + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "atviri-teises-aktai/1.0",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


def login() -> str:
    ts = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with tempfile.TemporaryDirectory() as d:
        msg, sig = pathlib.Path(d) / "ts", pathlib.Path(d) / "sig"
        msg.write_text(ts)
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(KEY), "-rawin", "-in", str(msg), "-out", str(sig)],
                       check=True, capture_output=True)
        signed = sig.read_bytes().hex()
    st, body = post("/v0.1/auth/http", {"domain": DOMAIN, "timestamp": ts, "signed_timestamp": signed})
    if st != 200:
        raise SystemExit(f"login failed: HTTP {st} {body}")
    return body["registry_token"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sj = server_json(a.version)
    print(json.dumps(sj, ensure_ascii=False, indent=1))
    if a.dry_run:
        return
    token = login()
    print("login: OK (token not shown)")
    st, body = post("/v0.1/publish", sj, token)
    print(f"publish: HTTP {st} {json.dumps(body, ensure_ascii=False)[:400] if isinstance(body, dict) else body}")


if __name__ == "__main__":
    main()
