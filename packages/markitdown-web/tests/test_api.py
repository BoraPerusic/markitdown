import sys
import types
import pytest
from httpx import AsyncClient


# Provide a fake markitdown implementation for tests
class FakeResult:
    def __init__(self, markdown: str):
        self.markdown = markdown


class FakeMarkItDown:
    def __init__(self, enable_plugins: bool = False):
        self.enable_plugins = enable_plugins

    def convert_uri(self, uri: str):  # noqa: D401
        return FakeResult(markdown=f"Converted: {uri}")


fake_module = types.ModuleType("markitdown")
fake_module.MarkItDown = FakeMarkItDown
sys.modules.setdefault("markitdown", fake_module)


from markitdown_web.config import WebConfig  # noqa: E402
from markitdown_web.app import create_app  # noqa: E402


@pytest.mark.anyio
async def test_healthz():
    app = create_app(WebConfig(api_key="key"))
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_requires_api_key():
    app = create_app(WebConfig(api_key="secret"))
    async with AsyncClient(app=app, base_url="http://test") as ac:
        files = {"file": ("a.txt", b"hello")}
        r = await ac.post("/api/convert", files=files)
        assert r.status_code == 401
        body = r.json()
        assert body["error"]["code"] == 401


@pytest.mark.anyio
async def test_convert_download_sets_attachment_header(tmp_path):
    app = create_app(WebConfig(api_key="k", enable_plugins=True))
    async with AsyncClient(app=app, base_url="http://test") as ac:
        files = {"file": ("report.pdf", b"%PDF-sample")}
        r = await ac.post("/api/convert?response=download", files=files, headers={"x-api-key": "k"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd and cd.endswith('"report.md"')
        assert r.text.startswith("Converted: file://")


@pytest.mark.anyio
async def test_convert_inline_compressed_mode(tmp_path):
    app = create_app(WebConfig(api_key="k"))
    async with AsyncClient(app=app, base_url="http://test") as ac:
        files = {"file": ("doc.txt", b"hello")}
        r = await ac.post("/api/convert?response=compressed", files=files, headers={"x-api-key": "k", "accept-encoding": "gzip"})
        assert r.status_code == 200
        # Starlette test client may not apply gzip, but response should be OK and text available
        assert r.headers["content-type"].startswith("text/markdown")
        assert "attachment" not in (r.headers.get("content-disposition") or "")


@pytest.mark.anyio
async def test_max_size_enforced_via_content_length():
    app = create_app(WebConfig(api_key="k", max_upload_mb=1))
    async with AsyncClient(app=app, base_url="http://test") as ac:
        files = {"file": ("big.bin", b"0" * (2 * 1024 * 1024))}
        # httpx sets content-length of the whole multipart; we simulate header override for route logic
        r = await ac.post("/api/convert", files=files, headers={"x-api-key": "k", "Content-Length": str(2 * 1024 * 1024)})
        assert r.status_code == 413
        assert r.json()["error"]["code"] == 413


    @pytest.mark.anyio
    async def test_bulk_zip_upload_returns_zip(tmp_path, monkeypatch):
        # Patch bulk_convert inside the app module to avoid invoking real converter
        import types as _types
        import zipfile as _zipfile
        import os as _os
        from markitdown_web import app as appmod

        class DummyBulkResult:
            def __init__(self, dest):
                self.dest = dest

        def fake_bulk_convert(root: str, dest: str, **kwargs):  # type: ignore
            # Create a couple of markdown files in dest and a report
            _os.makedirs(dest, exist_ok=True)
            with open(_os.path.join(dest, "a.md"), "w", encoding="utf-8") as f:
                f.write("A")
            with open(_os.path.join(dest, "process_report.md"), "w", encoding="utf-8") as f:
                f.write("report")
            return DummyBulkResult(dest)

        monkeypatch.setattr(appmod, "bulk_convert", fake_bulk_convert)
        monkeypatch.setattr(appmod, "BulkConvertThresholds", object)

        # Build a tiny zip upload with two files
        upload_zip_path = tmp_path / "upload.zip"
        with _zipfile.ZipFile(upload_zip_path, "w", compression=_zipfile.ZIP_DEFLATED) as z:
            z.writestr("dir/x.txt", "hello")
            z.writestr("y.pdf", "%PDF")

        app = create_app(WebConfig(api_key="k"))
        async with AsyncClient(app=app, base_url="http://test") as ac:
            with open(upload_zip_path, "rb") as fz:
                files = {"file": ("upload.zip", fz.read(), "application/zip")}
            r = await ac.post("/api/convert?response=download&confirm=true", files=files, headers={"x-api-key": "k"})
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("application/zip")
            # validate zip has our files
            from io import BytesIO
            import zipfile
            zf = zipfile.ZipFile(BytesIO(r.content))
            names = set(zf.namelist())
            assert "a.md" in names
            assert "process_report.md" in names
