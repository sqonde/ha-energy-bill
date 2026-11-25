"""Create or complete a GitHub release without replacing its asset."""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, msg, headers, fp)


def request(method, path, *, data=None, content_type="application/json"):
    url = path if path.startswith("https://") else f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}{path}"
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "Content-Type": content_type,
        "X-GitHub-Api-Version": "2022-11-28",
    })
    for attempt in range(3):
        try:
            with urllib.request.build_opener(NoRedirect()).open(req) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code < 500 or attempt == 2:
                raise
            time.sleep(5)


def asset_exists(release, name):
    for asset in release["assets"]:
        if asset["name"] == name:
            if asset["state"] != "uploaded":
                raise RuntimeError(f"Existing asset {name} is incomplete")
            return True
    return False


def publish(tag, archive):
    path = "/releases/tags/" + urllib.parse.quote(tag, safe="")
    try:
        release = request("GET", path)
    except HTTPError as error:
        if error.code != 404:
            raise
        try:
            release = request("POST", "/releases", data=json.dumps({
                "tag_name": tag, "name": tag, "generate_release_notes": True,
            }).encode())
        except HTTPError as create_error:
            if create_error.code not in (422, 500, 502, 503, 504):
                raise
            release = request("GET", path)
    if asset_exists(release, archive.name):
        return
    upload_url = release["upload_url"].split("{")[0]
    parsed = urllib.parse.urlsplit(upload_url)
    if parsed.scheme != "https" or parsed.netloc != "uploads.github.com":
        raise ValueError("Untrusted upload URL")
    url = upload_url + "?" + urllib.parse.urlencode({"name": archive.name})
    try:
        request("POST", url, data=archive.read_bytes(), content_type="application/zip")
    except HTTPError as error:
        if error.code not in (422, 500, 502, 503, 504):
            raise
        release = request("GET", path)
        if not asset_exists(release, archive.name):
            raise


if __name__ == "__main__":
    publish(sys.argv[1], Path(sys.argv[2]))
