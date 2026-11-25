"""Test the release archive produced by the workflow."""

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml


def test_release_archive_has_stamped_manifest_in_integration_directory(tmp_path):
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    step = next(s for s in workflow["jobs"]["release"]["steps"] if s.get("name") == "Build archive")
    shutil.copytree(root / "custom_components", tmp_path / "custom_components")
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    (tmp_path / "custom_components/energy_bill/secret.private").write_text("private")
    subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=tmp_path,
        env=os.environ | {"RELEASE_TAG": "v0.2.0"},
        check=True,
    )
    with zipfile.ZipFile(tmp_path / "energy_bill.zip") as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        assert set(archive.namelist()) == {
            str(path.relative_to(tmp_path / "custom_components"))
            for path in (tmp_path / "custom_components/energy_bill").rglob("*")
            if path.is_file() and path.name != "secret.private"
        }
        assert "energy_bill/manifest.json" in archive.namelist()
        assert "energy_bill/secret.private" not in archive.namelist()
        assert json.loads(archive.read("energy_bill/manifest.json"))["version"] == "0.2.0"


def test_release_archive_is_reproducible_when_checkout_times_change(tmp_path):
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    step = next(s for s in workflow["jobs"]["release"]["steps"] if s.get("name") == "Build archive")
    shutil.copytree(root / "custom_components", tmp_path / "custom_components")
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    env = os.environ | {"RELEASE_TAG": "v0.2.0"}
    subprocess.run(["bash", "-e", "-c", step["run"]], cwd=tmp_path, env=env, check=True)
    first = (tmp_path / "energy_bill.zip").read_bytes()
    for path in (tmp_path / "custom_components").rglob("*"):
        os.utime(path, (946684800, 946684800))
    subprocess.run(["bash", "-e", "-c", step["run"]], cwd=tmp_path, env=env, check=True)
    assert (tmp_path / "energy_bill.zip").read_bytes() == first


@pytest.mark.parametrize("failed_push", [False, True])
def test_tag_job_does_not_repeat_a_created_tag(tmp_path, failed_push):
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    step = next(s for s in workflow["jobs"]["tag"]["steps"] if s.get("id") == "bump")
    repo = tmp_path / "source"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    (repo / "file").write_text("test")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "test: initial"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "tag", "v0.1.0"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "ci: next"], cwd=repo, check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    git = bindir / "git"
    git.write_text(f'#!/bin/sh\nif [ "$1" = clone ]; then shift 2; exec /usr/bin/git clone "{repo}" "$@"; fi\nexec /usr/bin/git "$@"\n')
    git.chmod(0o755)
    bump = tmp_path / "bump"
    bump.write_text(
        '#!/bin/sh\n'
        + (f'echo called >> "{tmp_path}/calls"\ngit tag v0.2.0\ngit push origin refs/tags/v0.2.0\nexit 1\n' if failed_push else 'exit 0\n')
    )
    bump.chmod(0o755)
    output = tmp_path / "output"
    subprocess.run(
        ["bash", "-e", "-c", step["run"]], cwd=tmp_path, check=True,
        env=os.environ | {"PATH": f"{bindir}:{os.environ['PATH']}", "GH_TOKEN": "fake", "GITHUB_REPOSITORY": "test/repo", "GITHUB_SHA": sha, "GITHUB_OUTPUT": str(output), "BUMP_DIR": str(tmp_path)},
    )
    assert output.read_text() == ("tag=v0.2.0\n" if failed_push else "tag=\n")
    if failed_push:
        assert (tmp_path / "calls").read_text() == "called\n"
