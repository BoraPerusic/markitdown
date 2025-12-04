from __future__ import annotations

import os
import tempfile
from typing import Optional
import zipfile
import shutil
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Query, Depends, HTTPException, Header, Request
from fastapi.responses import PlainTextResponse, HTMLResponse, Response, JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED, HTTP_413_REQUEST_ENTITY_TOO_LARGE

from .config import WebConfig

try:
    from markitdown import MarkItDown  # type: ignore
except Exception:  # pragma: no cover
    MarkItDown = None  # type: ignore

# Bulk conversion support from core package (optional at import time for tests)
try:  # pragma: no cover - exercised in dedicated tests
    from markitdown.bulk_converter import (
        bulk_convert,
        BulkConvertThresholds,
    )  # type: ignore
except Exception:  # pragma: no cover
    bulk_convert = None  # type: ignore
    BulkConvertThresholds = None  # type: ignore


def create_app(config: WebConfig) -> FastAPI:
    app = FastAPI(title="MarkItDown Web", version="0.1.0")

    # GZip is how we provide the "compressed plaintext" behavior when requested by the client
    app.add_middleware(GZipMiddleware, minimum_size=512)

    if config.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Instantiate converter once at startup according to config
    if MarkItDown is None:
        raise RuntimeError("markitdown package is not available")
    converter = MarkItDown(enable_plugins=config.enable_plugins)

    async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
        if not x_api_key or x_api_key != config.api_key:
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="invalid or missing API key")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.status_code, "message": exc.detail}})

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception):  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": {"code": 500, "message": str(exc)}})

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/")
    async def index() -> HTMLResponse:
        # Minimal single-file UI with on-demand preview
        html = """
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>MarkItDown Web</title>
    <style>
      body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; height: 100vh; display: flex; flex-direction: column; }
      header { padding: 12px 16px; border-bottom: 1px solid #ddd; display: flex; gap: 8px; align-items: center; }
      main { flex: 1; display: flex; min-height: 0; }
      .pane { flex: 1; min-width: 0; display: flex; flex-direction: column; }
      .pane > .title { padding: 8px; border-bottom: 1px solid #eee; font-weight: 600; }
      #editor { flex: 1; min-height: 0; border-right: 1px solid #eee; }
      #preview { flex: 1; padding: 12px; overflow: auto; }
      #error { color: #b00020; padding-left: 8px; }
      button { padding: 6px 10px; }
      input[type="text"]{ padding: 6px; }
    </style>
    <script src=\"https://cdn.jsdelivr.net/npm/marked/marked.min.js\"></script>
    <script src=\"https://cdn.jsdelivr.net/npm/dompurify@3.1.7/dist/purify.min.js\"></script>
    <script>window.require = { paths: { 'vs': 'https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs' } };</script>
    <script src=\"https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs/loader.min.js\"></script>
  </head>
  <body>
    <header>
      <strong>MarkItDown Web</strong>
      <input type=\"file\" id=\"file\" />
      <input type=\"text\" id=\"apikey\" placeholder=\"API key\" size=\"24\" />
      <button id=\"upload\">Upload & Convert (download)</button>
      <button id=\"uploadInline\">Upload & Convert (inline)</button>
      <button id=\"previewBtn\">Update Preview</button>
      <button id=\"downloadMd\">Download .md</button>
      <span id=\"error\"></span>
    </header>
    <main>
      <div class=\"pane\">
        <div class=\"title\">Markdown Editor</div>
        <div id=\"editor\"></div>
      </div>
      <div class=\"pane\">
        <div class=\"title\">Preview</div>
        <div id=\"preview\"></div>
      </div>
    </main>
    <script>
      let editor;
      require(["vs/editor/editor.main"], function() {
        editor = monaco.editor.create(document.getElementById('editor'), {
          value: "",
          language: "markdown",
          automaticLayout: true,
          theme: (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'vs-dark' : 'vs'
        });
      });

      function setError(msg){ document.getElementById('error').textContent = msg || ''; }

      async function doUpload(asDownload){
        setError('');
        const f = document.getElementById('file').files[0];
        if(!f){ setError('Select a file first.'); return; }
        const apikey = document.getElementById('apikey').value.trim();
        const fd = new FormData();
        fd.append('file', f, f.name);
        const mode = asDownload ? 'download' : 'compressed';
        try{
          const res = await fetch(`/api/convert?response=${mode}`, { method: 'POST', body: fd, headers: { 'x-api-key': apikey }});
          if(!res.ok){ const text = await res.text(); setError(text || ('HTTP '+res.status)); return; }
          const cd = res.headers.get('Content-Disposition');
          const text = await res.text();
          editor.setValue(text);
          if(asDownload && cd){
            // Browser may already prompt download if server sends attachment; fallback not needed here
          }
        }catch(e){ setError(String(e)); }
      }

      document.getElementById('upload').onclick = () => doUpload(true);
      document.getElementById('uploadInline').onclick = () => doUpload(false);
      document.getElementById('previewBtn').onclick = () => {
        const md = editor ? editor.getValue() : '';
        const html = DOMPurify.sanitize(marked.parse(md || ''));
        document.getElementById('preview').innerHTML = html;
      };
      document.getElementById('downloadMd').onclick = () => {
        const md = editor ? editor.getValue() : '';
        const blob = new Blob([md], {type: 'text/markdown;charset=utf-8'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'document.md';
        a.click();
        URL.revokeObjectURL(a.href);
      };
    </script>
  </body>
</html>
        """
        return HTMLResponse(content=html)

    def _derive_output_name(orig_name: Optional[str]) -> str:
        if not orig_name:
            return "document.md"
        base = os.path.basename(orig_name)
        root, _ = os.path.splitext(base)
        return (root or "document") + ".md"

    @app.post("/api/convert", dependencies=[Depends(require_api_key)])
    async def convert(
        file: UploadFile = File(...),
        response: str = Query("download", pattern="^(download|compressed)$"),
        confirm: Optional[bool] = Query(default=None, description="Confirm proceeding when bulk thresholds exceeded"),
        content_length: Optional[int] = Header(default=None, convert_underscores=False, alias="Content-Length"),
    ) -> Response:
        # Enforce size limit using Content-Length when available
        if content_length is not None and content_length > config.max_upload_bytes:
            raise HTTPException(status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="upload too large")

        # Persist to a temporary file
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = tmp.name
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    # Best-effort enforcement for clients without Content-Length
                    if tmp.tell() + len(chunk) > config.max_upload_bytes:
                        raise HTTPException(status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="upload too large")
                    tmp.write(chunk)

            # Decide whether this is an archive for bulk processing (currently support .zip)
            is_zip = (file.filename or "").lower().endswith(".zip")
            if is_zip:
                if bulk_convert is None or BulkConvertThresholds is None:
                    raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="bulk conversion not available")

                extract_dir = tempfile.mkdtemp()
                dest_dir = tempfile.mkdtemp()
                try:
                    # Extract
                    with zipfile.ZipFile(tmp_path, 'r') as zf:
                        zf.extractall(extract_dir)

                    # Run bulk conversion with default thresholds; confirm must be True when exceeded
                    thresholds = BulkConvertThresholds(max_dirs=16, max_files=128, max_bytes=300*1024*1024)

                    def _confirm_cb(stats, thres):  # type: ignore
                        return bool(confirm)

                    result_bulk = bulk_convert(
                        root=extract_dir,
                        dest=dest_dir,
                        on_conflict="rename",
                        continue_on_error=True,
                        thresholds=thresholds,
                        confirm=_confirm_cb,
                        skip_hidden=True,
                    )

                    # Zip the dest_dir
                    out_zip_path = tempfile.NamedTemporaryFile(delete=False, suffix=".zip").name
                    with zipfile.ZipFile(out_zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as outzip:
                        for root_dir, _, files_in in os.walk(result_bulk.dest):
                            for fn in files_in:
                                full = Path(root_dir) / fn
                                rel = full.relative_to(result_bulk.dest)
                                outzip.write(full, arcname=str(rel))

                    # Prepare response
                    out_name = (Path(file.filename).stem if file.filename else "converted") + "-md.zip"
                    headers = {
                        "Content-Disposition": f"attachment; filename=\"{out_name}\"",
                        "Content-Type": "application/zip",
                    }
                    with open(out_zip_path, 'rb') as fzip:
                        data = fzip.read()
                    return Response(content=data, headers=headers, media_type="application/zip")
                except Exception as e:
                    # For threshold confirmation failures, provide structured message
                    raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"bulk conversion failed: {e}")
                finally:
                    try:
                        shutil.rmtree(extract_dir, ignore_errors=True)
                    except Exception:
                        pass
                    try:
                        shutil.rmtree(dest_dir, ignore_errors=True)
                    except Exception:
                        pass
            else:
                # Single file conversion via MarkItDown's URI API
                uri = f"file://{tmp_path}"
                result = converter.convert_uri(uri)
                markdown = result.markdown if hasattr(result, "markdown") else str(result)
        except HTTPException:
            # Reraise cleanly
            raise
        except Exception as e:  # pragma: no cover
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"conversion failed: {e}")
        finally:
            try:
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

        filename = _derive_output_name(file.filename)

        if response == "download":
            headers = {
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Content-Type": "text/markdown; charset=utf-8",
            }
            return PlainTextResponse(markdown, headers=headers)
        else:
            # compressed mode: rely on GZipMiddleware, return inline markdown
            return PlainTextResponse(markdown)

    return app
