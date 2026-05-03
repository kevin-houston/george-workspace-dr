#!/usr/bin/env python3
"""
Minimal here.now publisher — secure reimplementation.

Uses only Python stdlib (urllib, hashlib, json, pathlib).
No third-party packages, no bundled binaries, no shell execution.

Usage:
  python3 herenow.py <file_or_dir> [--slug SLUG] [--title TITLE]

Returns the live URL on stdout.
State (slug + claim token) is saved to ~/.herenow/state.json for updates.
"""

import sys
import json
import hashlib
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

BASE_URL = "https://here.now"
STATE_FILE = Path.home() / ".herenow" / "state.json"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm":  "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt":  "text/plain; charset=utf-8",
    ".md":   "text/plain; charset=utf-8",
    ".svg":  "image/svg+xml",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".pdf":  "application/pdf",
    ".ico":  "image/x-icon",
}

def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def collect_files(target: Path) -> list[dict]:
    """Return list of {path, abs_path, size, contentType, hash}."""
    files = []
    if target.is_file():
        files.append({
            "path": target.name,
            "abs_path": target,
            "size": target.stat().st_size,
            "contentType": content_type(target),
            "hash": sha256(target),
        })
    elif target.is_dir():
        for f in sorted(target.rglob("*")):
            if f.is_file() and f.name != ".DS_Store":
                rel = f.relative_to(target)
                files.append({
                    "path": str(rel),
                    "abs_path": f,
                    "size": f.stat().st_size,
                    "contentType": content_type(f),
                    "hash": sha256(f),
                })
    return files

def api_request(method: str, url: str, body: Optional[dict] = None,
                api_key: Optional[str] = None) -> dict:
    """Make a JSON API request, return parsed response."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "x-herenow-client": "george-pead-tracker/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        try:
            err = json.loads(body_text)
            raise RuntimeError(f"API error {e.code}: {err.get('error', body_text)}")
        except json.JSONDecodeError:
            raise RuntimeError(f"API error {e.code}: {body_text}")

def upload_file(url: str, path: Path, ct: str) -> None:
    """PUT a single file to the pre-signed upload URL."""
    with open(path, "rb") as f:
        data = f.read()
    headers = {"Content-Type": ct}
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=60):
            pass
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Upload failed for {path.name}: HTTP {e.code}")

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"publishes": {}}

def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def publish(target: Path, slug: Optional[str] = None,
            title: Optional[str] = None, api_key: Optional[str] = None) -> str:
    """Publish a file or directory. Returns the live URL."""
    files = collect_files(target)
    if not files:
        raise RuntimeError(f"No files found in {target}")

    print(f"Publishing {len(files)} file(s)...", file=sys.stderr)

    # Build manifest (without abs_path for API)
    manifest = [{"path": f["path"], "size": f["size"],
                 "contentType": f["contentType"], "hash": f["hash"]}
                for f in files]

    body: dict = {"files": manifest}
    if title:
        body["viewer"] = {"title": title}

    # Load claim token for anonymous updates
    state = load_state()
    if slug and not api_key:
        claim_token = state.get("publishes", {}).get(slug, {}).get("claimToken")
        if claim_token:
            body["claimToken"] = claim_token

    # Step 1: Create or update publish
    if slug:
        resp = api_request("PUT", f"{BASE_URL}/api/v1/publish/{slug}", body, api_key)
    else:
        resp = api_request("POST", f"{BASE_URL}/api/v1/publish", body, api_key)

    out_slug    = resp["slug"]
    site_url    = resp["siteUrl"]
    version_id  = resp["upload"]["versionId"]
    finalize_url = resp["upload"]["finalizeUrl"]
    uploads     = resp["upload"]["uploads"]
    skipped     = len(resp["upload"].get("skipped", []))

    print(f"Uploading {len(uploads)} file(s) ({skipped} unchanged)...", file=sys.stderr)

    # Build path → file info lookup
    file_map = {f["path"]: f for f in files}

    # Step 2: Upload files
    for u in uploads:
        info = file_map.get(u["path"])
        if not info:
            raise RuntimeError(f"Upload path not found locally: {u['path']}")
        upload_file(u["url"], info["abs_path"], info["contentType"])

    # Step 3: Finalize
    print("Finalizing...", file=sys.stderr)
    api_request("POST", finalize_url, {"versionId": version_id}, api_key)

    # Persist state
    entry: dict = {"siteUrl": site_url}
    if "claimToken" in resp:
        entry["claimToken"] = resp["claimToken"]
    if "expiresAt" in resp:
        entry["expiresAt"] = resp["expiresAt"]
    state.setdefault("publishes", {})[out_slug] = entry
    save_state(state)

    return site_url

def main():
    parser = argparse.ArgumentParser(description="Publish files to here.now")
    parser.add_argument("target", help="File or directory to publish")
    parser.add_argument("--slug", help="Update existing publish by slug")
    parser.add_argument("--title", help="Page title")
    parser.add_argument("--api-key", help="here.now API key (or set HERENOW_API_KEY)")
    args = parser.parse_args()

    import os
    api_key = args.api_key or os.environ.get("HERENOW_API_KEY")

    target = Path(args.target)
    if not target.exists():
        print(f"error: path does not exist: {target}", file=sys.stderr)
        sys.exit(1)

    url = publish(target, slug=args.slug, title=args.title, api_key=api_key)
    print(url)

if __name__ == "__main__":
    main()
