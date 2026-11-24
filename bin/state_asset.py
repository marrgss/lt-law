#!/usr/bin/env python3
"""The nightly's state asset (release `state`, state.tar.zst): pack data/ into a new one, compare, upload.

Usage: uv run bin/state_asset.py pack [--state DIR] [--allow-removals]
       uv run bin/state_asset.py upload

pack     downloads the asset now on GitHub into private/backups/<date>/ (the way back), packs data/{state, dokumentas,
         amending, suvestine, decisions} as the workflow does into out/state.tar.zst, and lists what changed. A file in
         the old asset but not in the new one stops it (the nightly would lose it): --allow-removals when that is meant.
         --state: the state folder to pack (bin/add_acts.py's out/add/<batch>/state.before-gate: data/state before the
         gate wrote tonight's ledger and manifest into it).
upload   uploads out/state.tar.zst with --clobber, refusing while a nightly runs or waits (it restores the asset at its
         start and saves it at its end: an upload in between is lost, or loses the night's).
"""
import argparse
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "state.tar.zst"
PARTS = ["dokumentas", "amending", "suvestine", "decisions"]
# packed only when present: the Seimas votes (D-054) are on once data/seimas is in the asset (the nightly fetches the newest
# term when it finds the folder; earlier terms are closed and kept here)
OPTIONAL = ["seimas"]


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def members(path: pathlib.Path) -> dict[str, int]:
    """name -> size of every file in a .tar.zst."""
    with tempfile.TemporaryDirectory() as d:
        tar = pathlib.Path(d) / "x.tar"
        subprocess.run(["zstd", "-q", "-d", str(path), "-o", str(tar)], check=True)
        with tarfile.open(tar) as t:
            return {m.name.removeprefix("./"): m.size for m in t.getmembers() if m.isfile()}


def manifest_day(path: pathlib.Path) -> str:
    """The last build's day in a .tar.zst (state/manifest.json)."""
    r = subprocess.run(["tar", "--zstd", "-xOf", str(path), "state/manifest.json"], capture_output=True, text=True)
    return json.loads(r.stdout).get("day", "") if r.returncode == 0 and r.stdout else ""


def pack(state: pathlib.Path, allow_removals: bool) -> None:
    backup = ROOT / "private" / "backups" / dt.date.today().isoformat()
    backup.mkdir(parents=True, exist_ok=True)
    old = backup / f"state-{dt.datetime.now().strftime('%H%M%S')}.tar.zst"
    with tempfile.TemporaryDirectory() as d:
        gh("release", "download", "state", "--pattern", "state.tar.zst", "--dir", d)
        shutil.move(pathlib.Path(d, "state.tar.zst"), old)  # /tmp may be another file system (tmpfs): no rename
    print(f"the asset on GitHub: {old} ({old.stat().st_size / 1e6:.1f} MB)")
    data = ROOT / "data"
    with tempfile.TemporaryDirectory() as d:  # the state folder under its published name, whatever its path here
        root = pathlib.Path(d)
        (root / "state").symlink_to(state.resolve())
        for p in PARTS:
            (data / p).mkdir(exist_ok=True)
            (root / p).symlink_to((data / p).resolve())
        extra = [p for p in OPTIONAL if (data / p).is_dir() and any((data / p).iterdir())]
        for p in extra:
            (root / p).symlink_to((data / p).resolve())
        OUT.parent.mkdir(exist_ok=True)
        subprocess.run(["tar", "-I", "zstd -19 -T0", "-chf", str(OUT), "-C", d, "state", *PARTS, *extra], check=True)
    a, b = members(old), members(OUT)
    # a night ran since data/ was read: packing would put its ledger, manifest and texts back to the older ones
    if (mine := manifest_day(OUT)) < (theirs := manifest_day(old)):
        OUT.unlink()
        sys.exit(f"the asset on GitHub is from {theirs}, data/ from {mine}: extract the asset into data/ first (a nightly ran)")
    gone = sorted(set(a) - set(b))
    added = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    print(f"new: {OUT} ({OUT.stat().st_size / 1e6:.1f} MB): {len(added)} files added, {len(changed)} changed, {len(gone)} gone")
    for k in changed[:15]:
        print(f"  changed {k}: {a[k]} -> {b[k]} B")
    if gone:
        print("  gone: " + ", ".join(gone[:20]) + (" …" if len(gone) > 20 else ""))
        if not allow_removals:
            OUT.unlink()
            sys.exit("files would be lost from the asset: not packed (--allow-removals if that is meant)")


def upload() -> None:
    if not OUT.exists():
        sys.exit(f"{OUT} missing: run pack first")
    busy = [r for s in ("in_progress", "queued") for r in gh("run", "list", "--workflow", "nightly", "--status", s,
                                                             "--json", "databaseId", "--jq", ".[].databaseId").split()]
    if busy:
        sys.exit(f"a nightly runs or waits ({', '.join(busy)}): not uploaded; try after it ends")
    gh("release", "upload", "state", str(OUT), "--clobber")
    print(f"uploaded {OUT.stat().st_size / 1e6:.1f} MB to release 'state'")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["pack", "upload"])
    ap.add_argument("--state", type=pathlib.Path, default=ROOT / "data" / "state")
    ap.add_argument("--allow-removals", action="store_true")
    a = ap.parse_args()
    pack(a.state, a.allow_removals) if a.what == "pack" else upload()


if __name__ == "__main__":
    main()
