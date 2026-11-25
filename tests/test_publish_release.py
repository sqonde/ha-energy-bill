"""Exercise release recovery against a local GitHub API stand-in."""

import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest


def load_publisher():
    path = Path(__file__).resolve().parents[1] / "scripts/publish_release.py"
    spec = importlib.util.spec_from_file_location("publish_release", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_asset_is_never_replaced(monkeypatch, tmp_path):
    publisher = load_publisher()
    archive = tmp_path / "energy_bill.zip"
    archive.write_bytes(b"new")
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path))
        return {"assets": [{"name": "energy_bill.zip", "state": "uploaded"}], "upload_url": "https://uploads.github.com/{?name,label}"}

    monkeypatch.setattr(publisher, "request", request)
    publisher.publish("v0.3.2", archive)
    assert calls == [("GET", "/releases/tags/v0.3.2")]


def test_retries_server_errors_and_stops_on_client_errors(monkeypatch):
    publisher = load_publisher()
    monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
    monkeypatch.setenv("GH_TOKEN", "test")
    outcomes = [500, 504, 200]
    monkeypatch.setattr(publisher.time, "sleep", lambda _: None)

    def open_url(request):
        status = outcomes.pop(0)
        if status != 200:
            raise HTTPError(request.full_url, status, "failure", {}, io.BytesIO(b"error"))
        return io.BytesIO(json.dumps({"ok": True}).encode())

    class Opener:
        open = staticmethod(open_url)

    monkeypatch.setattr(publisher.urllib.request, "build_opener", lambda *args: Opener())
    assert publisher.request("GET", "/test") == {"ok": True}
    outcomes[:] = [403, 200]
    with pytest.raises(HTTPError):
        publisher.request("GET", "/test")
    assert outcomes == [200]


def test_create_release_and_upload_missing_asset(monkeypatch, tmp_path):
    publisher = load_publisher()
    archive = tmp_path / "energy_bill.zip"
    archive.write_bytes(b"archive")
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            raise HTTPError(path, 404, "missing", {}, None)
        if path == "/releases":
            return {"assets": [], "upload_url": "https://uploads.github.com/upload{?name,label}"}
        return {"name": "energy_bill.zip", "state": "uploaded"}

    monkeypatch.setattr(publisher, "request", request)
    publisher.publish("v0.3.2", archive)
    assert json.loads(calls[1][2]["data"]) == {
        "tag_name": "v0.3.2", "name": "v0.3.2", "generate_release_notes": True,
    }
    assert calls[2] == ("POST", "https://uploads.github.com/upload?name=energy_bill.zip", {
        "data": b"archive", "content_type": "application/zip",
    })


def test_recovers_when_create_succeeded_but_response_failed(monkeypatch, tmp_path):
    publisher = load_publisher()
    archive = tmp_path / "energy_bill.zip"
    archive.write_bytes(b"archive")
    replies = iter([404, 422, {"assets": [{"name": "energy_bill.zip", "state": "uploaded"}]}])

    def request(method, path, **kwargs):
        reply = next(replies)
        if isinstance(reply, int):
            raise HTTPError(path, reply, "failure", {}, None)
        return reply

    monkeypatch.setattr(publisher, "request", request)
    publisher.publish("v0.3.2", archive)
    assert next(replies, None) is None


def test_incomplete_existing_asset_fails_without_replacing_it(monkeypatch, tmp_path):
    publisher = load_publisher()
    archive = tmp_path / "energy_bill.zip"
    monkeypatch.setattr(publisher, "request", lambda *args, **kwargs: {
        "assets": [{"name": "energy_bill.zip", "state": "starter"}],
    })
    with pytest.raises(RuntimeError, match="incomplete"):
        publisher.publish("v0.3.2", archive)


def test_rejects_untrusted_upload_url_without_sending_archive(monkeypatch, tmp_path):
    publisher = load_publisher()
    archive = tmp_path / "energy_bill.zip"
    archive.write_bytes(b"archive")
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path))
        return {"assets": [], "upload_url": "https://evil.example/upload{?name,label}"}

    monkeypatch.setattr(publisher, "request", request)
    with pytest.raises(ValueError, match="upload URL"):
        publisher.publish("v0.3.2", archive)
    assert calls == [("GET", "/releases/tags/v0.3.2")]


def test_rejects_redirects():
    publisher = load_publisher()
    handler = publisher.NoRedirect()
    with pytest.raises(HTTPError):
        handler.redirect_request(publisher.urllib.request.Request("https://api.github.com"), None, 302, "redirect", {}, "https://evil.example")
