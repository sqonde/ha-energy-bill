"""Tests for the release archive."""

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path


def test_release_archive_contains_only_integration(tmp_path):
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "init", "--bare", str(tmp_path / "origin.git")],
        check=True,
        capture_output=True,
    )
    for key, value in (("user.name", "test"), ("user.email", "test@example.invalid")):
        subprocess.run(["git", "config", key, value], cwd=repo, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", str(tmp_path / "origin.git")],
        cwd=repo,
        check=True,
    )
    shutil.copytree(
        root / "custom_components",
        repo / "custom_components",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copytree(root / "scripts", repo / "scripts")
    (repo / ".gitignore").write_text("*.private\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "test: initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    tools = tmp_path / "bin"
    tools.mkdir()
    gh = tools / "gh"
    gh.write_text('#!/bin/sh\ncp "$4" "$RELEASE_ARCHIVE"\n')
    gh.chmod(0o755)
    archive = tmp_path / "release.zip"
    env = os.environ | {
        "PATH": f"{tools}:{os.environ['PATH']}",
        "RELEASE_ARCHIVE": str(archive),
    }
    (repo / "custom_components/energy_bill/secret.private").write_text("private")
    subprocess.run(
        ["scripts/release.sh", "0.2.0"],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
    )
    with zipfile.ZipFile(archive) as result:
        assert "energy_bill/manifest.json" in result.namelist()
        assert "energy_bill/secret.private" not in result.namelist()
        assert all(
            name.startswith("energy_bill/") and "__pycache__" not in name
            for name in result.namelist()
        )
        assert (
            json.loads(result.read("energy_bill/manifest.json"))["version"] == "0.2.0"
        )
