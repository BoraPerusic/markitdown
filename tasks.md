# MarkItDown Web Wrapper — Project Plan

This document outlines the plan to add a new package `markitdown-web` that exposes MarkItDown conversions over HTTP and provides a simple browser UI with an editor/preview split view. This step is planning-only; no code changes have been made yet.

## Goals and Scope

- Provide a lightweight web service wrapping the existing `markitdown` package:
  - API: Accept file uploads via POST and return converted Markdown either as a downloadable `.md` file or a compressed plaintext payload (exact format TBD).
  - Web UI: A page with a file uploader that performs conversion and displays results in a split view: Monaco editor (markdown mode) on the left and live preview on the right; user can download the edited `.md`.
- Package this as a standalone installable package under `packages/markitdown-web` within the monorepo.
- Do not change the core `markitdown` library; only wrap it.

## Proposed Architecture (for review)

- New package: `packages/markitdown-web`
  - Framework: FastAPI (built on Starlette) for API and minimal HTML UI routes, uvicorn for local server.
  - Endpoints:
    - `POST /api/convert?response=download|compressed` — multipart form with a single `file` field. Returns either:
      - `download`: `Content-Type: text/markdown` served as attachment with a filename derived from the upload.
      - `compressed`: Compressed plaintext payload; exact encoding TBD (see Open Questions).
    - `GET /` — serves the web UI (static HTML + JS). Monaco via CDN, client-side markdown preview using a common library (e.g., Marked or micromark). No frontend build tooling required initially.
  - Error handling: structured JSON for API errors, friendly messages in UI.
  - Security: file size limits, mime/extension hints only (trust the converter for sniffing), in-memory or temp storage, CORS optional.
  - Config: environment variables for max upload size, plugin enablement passthrough to `MarkItDown`, logging level.

## Detailed Task List

### 1. Repository and Package Scaffolding
- [ ] Create new directory `packages/markitdown-web`.
- [ ] Add `pyproject.toml` with project metadata, dependencies (FastAPI, uvicorn, python-multipart), and console script entry point `markitdown-web`.
- [ ] Add `README.md` for the new package with usage instructions and examples.
- [ ] Add `src/markitdown_web/__init__.py` and `__about__.py` (align with monorepo conventions).
- [ ] Add `src/markitdown_web/__main__.py` that boots the web server.
- [ ] Add `LICENSE` reference and `py.typed` if needed.

### 2. API Design and Implementation
- [ ] Define request contract for file upload:
  - [ ] Accept multipart with part name `file` (single file).
  - [ ] Optional query params: `response=download|compressed` (default TBD), `use_plugins=true|false` (optional), `filename` override (optional).
- [ ] Implement `POST /api/convert`:
  - [ ] Read file stream and original filename.
  - [ ] Use `markitdown.MarkItDown` with optional plugin toggle.
  - [ ] Call appropriate `convert_stream` or `convert_local` depending on temp handling.
  - [ ] Produce success response according to `response` mode.
  - [ ] Produce structured error JSON (`{"error": {"code": ..., "message": ...}}`).
  - [ ] Enforce maximum upload size with graceful error (413).
- [ ] Decide handling for non-text outputs (e.g., images extracted). For v1, return markdown only; note limitations in docs.
- [ ] Add simple health check `GET /healthz`.

### 3. Web UI Page
- [ ] Add route `GET /` serving a static HTML page with:
  - [ ] File input and upload button.
  - [ ] Split pane layout (CSS flex) with Monaco editor and live preview.
  - [ ] Client-side JS to upload to `/api/convert` and populate the editor.
  - [ ] Client-side markdown preview using a library (e.g., Marked.js) with basic sanitization.
  - [ ] “Download .md” button that downloads current editor content.
  - [ ] Basic error display area.
- [ ] Serve Monaco via CDN; no bundler required initially.
- [ ] Minimal responsive styles; dark/light mode optional.

### 4. Compression Option (API)
- [ ] Define the “compressed plaintext” response format:
  - [ ] Option A (preferred): `Content-Encoding: gzip` with `Content-Type: text/markdown; charset=utf-8` (body is gzipped). Clients must send `Accept-Encoding: gzip` to benefit; otherwise return identity. This leverages HTTP semantics.
  - [ ] Option B: Return `application/gzip` body containing the `.md` file. Filename via `Content-Disposition`. Less transparent, but explicit.
  - [ ] Option C: Return base64 string in JSON (`{"encoding":"base64","data":"..."}`) — simple but verbose.
- [ ] Implement the chosen approach consistently and document it. See Open Questions for decision.

### 5. Configuration and Ops
- [ ] Environment variables:
  - [ ] `MARKITDOWN_ENABLE_PLUGINS` (reuse semantics from MCP package).
  - [ ] `MARKITDOWN_WEB_MAX_UPLOAD_MB` (default TBD, e.g., 25 MiB).
  - [ ] `MARKITDOWN_WEB_LOG_LEVEL` (info/debug).
  - [ ] `MARKITDOWN_WEB_CORS_ORIGINS` (optional, comma-separated).
- [ ] Logging setup with uvicorn and app logger alignment.
- [ ] Graceful error pages for UI.

### 6. Packaging, Docker, and Run Targets
- [ ] Add `markitdown-web` to the root Dockerfile build (optional initial step) or create a dedicated Dockerfile under the package.
- [ ] Provide `uvicorn` CLI entry via `markitdown_web.__main__` (e.g., `markitdown-web --host 0.0.0.0 --port 8080`).
- [ ] Document production run guidance (e.g., `uvicorn --workers N`, behind reverse proxy serving gzip/brotli).

### 7. Security and Compliance
- [ ] Set conservative default max upload size and validate content length.
- [ ] Use temp files safely (NamedTemporaryFile) if required; otherwise process in-memory with stream limits.
- [ ] Sanitize markdown preview rendering (XSS prevention) in the browser (Marked + DOMPurify or equivalent).
- [ ] CORS: disabled by default; enable via env when embedding elsewhere.
- [ ] Rate limiting and auth are out of scope for v1; note in docs (see Open Questions).

### 8. Testing
- [ ] Unit tests for API:
  - [ ] Happy path upload and markdown download response.
  - [ ] `response=compressed` behavior per chosen approach.
  - [ ] Max size exceeded returns 413.
  - [ ] Plugin toggle env/param flows through to `MarkItDown`.
  - [ ] Error handling when converter raises.
- [ ] Simple UI smoke test (serve page and basic DOM elements present).
- [ ] Integration tests using `httpx.AsyncClient` against the ASGI app.
- [ ] If Docker is provided, add a basic container startup check (optional).

### 9. Documentation
- [ ] Update root `README.md` with a brief section referencing `markitdown-web` and usage examples (no breaking changes to existing docs).
- [ ] Add `packages/markitdown-web/README.md` with:
  - [ ] Installation and run instructions.
  - [ ] API contract and examples (curl and JS fetch).
  - [ ] UI screenshots or GIF (optional later).
  - [ ] Limitations and security notes.

### 10. Release and Versioning
- [ ] Decide versioning scheme for `markitdown-web` aligned with the monorepo (independent vs. tied to core).
- [ ] Publish to PyPI (optional per your release process) and/or document local editable install.
- [ ] Tag and changelog entry.

### 11. Nice-to-Have (Post-v1, optional)
- [ ] Streaming upload and progressive conversion feedback (Server-Sent Events or websockets).
- [ ] Support URL inputs and clipboard paste in UI.
- [ ] Multi-file batch conversion with zip download.
- [ ] Persist recent conversions in browser localStorage (optional).
- [ ] Theming and keyboard shortcuts for the editor.

## Assumptions and Defaults (please confirm)

- [ ] Use FastAPI + uvicorn; keep dependencies minimal (no frontend build tools).
- [ ] Default port 8080 for `markitdown-web` CLI.
- [ ] Single-file upload only for v1; returns only markdown text produced by `MarkItDown`.
- [ ] No authentication by default; to be deployed behind a reverse proxy if needed.
- [ ] Max upload size default: 25 MiB.
- [ ] Plugin usage disabled by default; can be enabled via `MARKITDOWN_ENABLE_PLUGINS=true` or query param.
- [ ] UI uses Monaco via CDN and Marked.js + DOMPurify for preview.
- [ ] Filenames: derive output name by replacing extension with `.md`; fallback to `document.md` if unknown.

## Open Questions

Please help clarify the following before implementation:

1. Response format for “compressed plaintext”:
   - Prefer standard HTTP compression (`Content-Encoding: gzip`) with `text/markdown`. Is this acceptable, or do you want a `.gz` file (`application/gzip`) or base64 JSON payload?
   - [standard HTTP compression is fine]
2. Query parameter name for output mode:
   - Is `response=download|compressed` acceptable, or do you prefer `mode=...` or `format=...`? What should be the default when omitted?
   - [response= is ok. If omitted, default to download the md file]
3. Size limits and performance:
   - What maximum upload size should we enforce by default? Any memory constraints we should target?
   - [configurable in the application / package configuration. Please, create a config file. Initial value would be 10 MiB]
4. Plugins:
   - Should the web service expose a toggle to enable plugins per-request, or only via env? Any plugins you specifically want enabled/disabled?
   - [Please, enable config file for the web service. The env variables are allowed and should overwrite the confg file if both are present. The plugins should be loaded at application start, no need to expose them to the user]
5. Security:
   - Do you require CORS support out of the box? If so, which origins?
   - [no CORS for the time being]
   - Any need for simple auth (API key, basic auth) in v1?
   - [API key please]
6. UI details:
   - Is a single-page minimal UI acceptable (no build step), or do you want a more polished layout/theme?
   - [single page is ok]
   - Do you want live preview to update on each keystroke, or on demand with a button for performance?
   - [on demand only]
7. Filenames and content disposition:
   - For `download` mode, is `Content-Disposition: attachment; filename="<base>.md"` the desired behavior?
   - [yes]
8. Error reporting:
   - Any preferred error schema for the API (fields / codes)? Is a simple `{error: {code, message}}` sufficient?
   - [yes]
9. Docker and deployment:
   - Should we add a dedicated Dockerfile for `markitdown-web`, or reuse/extend the root Dockerfile? Any base image preferences?
   - [Please, add dedicated docker for the web service. Any ubuntu is fine]
10. Browser support:
    - Any minimum browser targets we should keep in mind?
    - [Chrome and Edge]
11. Internationalization:
    - Do you need i18n/localization support in the UI for v1?
    - [No]
12. Telemetry:
    - Any logging/analytics requirements beyond access logs (e.g., anonymized metrics)?
    - [No]
13. CI integration:
    - Should we add tests for `markitdown-web` into existing CI pipelines here, and which Python versions to target?
    - [YEs, please, target Python v 3.13]

## Acceptance Criteria (v1)

- [ ] New package `markitdown-web` exists with a runnable CLI `markitdown-web`.
- [ ] `POST /api/convert` accepts a file and returns converted markdown per selected mode.
- [ ] `GET /` serves a working page with upload, Monaco editor, live preview, and download edited content.
- [ ] Size limits, basic error handling, and documented behavior are in place.
- [ ] Documentation updated with clear instructions and examples.

---

If you approve the plan and clarify the Open Questions, I will proceed with implementation following the checklist above.
