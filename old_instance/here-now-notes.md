# here.now — Agent Web Publishing Platform

URL: https://here.now/
Docs: https://here.now/docs

## What It Is
Free instant static web hosting for AI agents. Publish HTML, CSS, JS, images, PDFs, videos.
Sites go live at `https://<slug>.here.now/` within seconds.
No account needed — anonymous sites live 24 hours, can be claimed with an account.

## Use Cases
Documents, dashboards, tools, visualizations, presentations, prototypes, galleries, media files.
Static only — no backend, no databases, no server-side code.

## Three-Step Publish Flow

### Step 1 — Create site
POST https://here.now/api/v1/publish

Request body:
```json
{
  "files": [
    {
      "path": "index.html",
      "size": 1234,
      "contentType": "text/html; charset=utf-8",
      "hash": "optional-sha256"
    }
  ],
  "ttlSeconds": null,
  "viewer": {
    "title": "My site",
    "description": "Published by an agent"
  }
}
```

Response:
```json
{
  "slug": "bright-canvas-a7k2",
  "siteUrl": "https://bright-canvas-a7k2.here.now/",
  "upload": {
    "versionId": "01J...",
    "uploads": [...],
    "finalizeUrl": "https://here.now/api/v1/publish/bright-canvas-a7k2/finalize",
    "expiresInSeconds": 3600
  }
}
```

### Step 2 — Upload files
PUT to each presigned URL from the uploads array:
```bash
curl -X PUT "<presigned-url>" \
  -H "Content-Type: text/html" \
  --data-binary @index.html
```
Uploads can run in parallel. Presigned URLs valid for 1 hour.

### Step 3 — Finalize
POST https://here.now/api/v1/publish/<slug>/finalize
Body: { "versionId": "01J..." }

## Authentication
Add header: Authorization: Bearer <API_KEY>
Anonymous: skip header, 24hr expiry, 250MB max file size
Authenticated: 5GB max, persistent until deleted

## Notes
- Incremental deploys: include SHA-256 hash, unchanged files are copied not re-uploaded
- URL refresh: POST /api/v1/publish/<slug>/uploads/refresh if presigned URLs expire
- Works with Claude, Cursor, Codex, any HTTP client
- Cloudflare edge CDN, global delivery

## Ideas for Use with George
- Robinhood portfolio dashboard
- Daily AI podcast episode pages
- Paper trading reports
- Any visualizations/charts Kevin wants to share
