#!/usr/bin/env python3
"""Upload the dated-answers tree (bin/export_history.py) to the R2 bucket, only what is new or changed (D-029).

Usage: uv run bin/upload_history.py [out/history] [--bucket lt-law-history] [--apply]

Without --apply it lists what it would upload. Credentials from the environment (~/.config/lt-law/.env):
R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT (https://<account>.r2.cloudflarestorage.com), an R2 API token
with Object Read & Write on that one bucket. Uses R2's S3 API with AWS Signature V4, standard library only.
Remembers what it uploaded (out/history/.uploaded.json: object -> content hash), so a nightly run sends only
new versions; article objects are content-addressed and never change.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def put(endpoint: str, bucket: str, key: str, body: bytes, access: str, secret: str) -> int:
    """PUT one object (S3 SigV4, region "auto"); returns the HTTP status."""
    host = urllib.parse.urlparse(endpoint).netloc
    now = dt.datetime.now(dt.timezone.utc)
    amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    path = "/" + bucket + "/" + urllib.parse.quote(key, safe="/-_.~")
    payload = hashlib.sha256(body).hexdigest()
    headers = {"host": host, "x-amz-content-sha256": payload, "x-amz-date": amz, "content-type": "application/json"}
    signed = ";".join(sorted(headers))
    canonical = "\n".join(["PUT", path, "", "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)), signed, payload])
    scope = f"{day}/auto/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _sign(_sign(_sign(_sign(("AWS4" + secret).encode(), day), "auto"), "s3"), "aws4_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(endpoint.rstrip("/") + path, data=body, method="PUT", headers={
        **{h: v for h, v in headers.items() if h != "host"},
        "Authorization": f"AWS4-HMAC-SHA256 Credential={access}/{scope}, SignedHeaders={signed}, Signature={sig}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tree", nargs="?", type=pathlib.Path, default=pathlib.Path("out/history"))
    ap.add_argument("--bucket", default="lt-law-history")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    state_p = a.tree / ".uploaded.json"
    state = json.loads(state_p.read_text()) if state_p.exists() else {}
    todo = []
    for p in sorted(a.tree.rglob("*.json")):
        if p.name.startswith("."):
            continue
        key = p.relative_to(a.tree).as_posix()
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if state.get(key) != h:
            todo.append((key, p, h))
    print(f"{len(todo)} of {sum(1 for p in a.tree.rglob('*.json') if not p.name.startswith('.'))} objects new or changed"
          f" ({sum(p.stat().st_size for _, p, _ in todo) / 1e6:.1f} MB)")
    if not a.apply:
        for key, _, _ in todo[:10]:
            print("  +", key)
        print("dry run: add --apply to upload")
        return
    access, secret, endpoint = (os.environ.get(k, "").strip() for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT"))
    if not (access and secret and endpoint):
        sys.exit("R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_ENDPOINT are needed (docs/OPERATIONS.md)")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    done = 0
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:  # 8 at a time: the same writes, minutes instead of hours
            futs = {pool.submit(put, endpoint, a.bucket, key, p.read_bytes(), access, secret): (key, h) for key, p, h in todo}
            for f in as_completed(futs):
                key, h = futs[f]
                f.result()  # an error stops the run; what was done is remembered
                state[key] = h
                done += 1
                if done % 2000 == 0:
                    state_p.write_text(json.dumps(state))
                    print(f"  {done} uploaded")
    finally:
        state_p.write_text(json.dumps(state))
    print(f"uploaded {done}")


if __name__ == "__main__":
    main()
