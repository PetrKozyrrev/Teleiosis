"""Failure paths must never overwrite an archive or restore into live data."""

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_docker(tmp_path):
    executable = tmp_path / "docker"
    executable.write_text(
        '#!/bin/sh\n'
        'case "$*" in\n'
        '  *pg_dump*) printf "partial-archive"; exit "${DUMP_EXIT:-0}" ;;\n'
        '  *pg_restore*) cat > /dev/null; exit "${RESTORE_EXIT:-0}" ;;\n'
        '  *) exit 77 ;;\n'
        'esac\n'
    )
    executable.chmod(0o700)
    env_file = tmp_path / "synthetic.env"
    env_file.write_text("# No real credentials\n")
    return {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "TELEIOSIS_ENV_FILE": str(env_file),
    }


@pytest.mark.parametrize("target", ["teleiosis", "teleiosis_restore_test_x;drop", "teleiosis_restore_test_" + "a" * 64])
def test_restore_refuses_unsafe_target_without_docker(tmp_path, target):
    archive = tmp_path / "backup.dump"
    archive.write_bytes(b"synthetic")
    result = subprocess.run(
        ["sh", "deploy/restore-check.sh", str(archive), target], cwd=ROOT,
        capture_output=True, text=True,
    )
    assert result.returncode == 2


@pytest.mark.parametrize("failure", ["DUMP_EXIT", "RESTORE_EXIT"])
def test_backup_does_not_publish_failed_archive(tmp_path, fake_docker, failure):
    archive = tmp_path / "backup.dump"
    result = subprocess.run(
        ["sh", "deploy/backup.sh", str(archive)], cwd=ROOT,
        env={**fake_docker, failure: "1"}, capture_output=True,
    )
    assert result.returncode != 0
    assert not archive.exists()
    assert Path(f"{archive}.partial").exists()


def test_backup_never_replaces_existing_archive(tmp_path, fake_docker):
    archive = tmp_path / "backup.dump"
    archive.write_bytes(b"keep-original")
    result = subprocess.run(
        ["sh", "deploy/backup.sh", str(archive)], cwd=ROOT,
        env=fake_docker, capture_output=True,
    )
    assert result.returncode != 0
    assert archive.read_bytes() == b"keep-original"


def test_backup_publishes_private_archive_after_validation(tmp_path, fake_docker):
    archive = tmp_path / "backup.dump"
    result = subprocess.run(
        ["sh", "deploy/backup.sh", str(archive)], cwd=ROOT,
        env=fake_docker, capture_output=True,
    )
    assert result.returncode == 0
    assert archive.read_bytes() == b"partial-archive"
    assert archive.stat().st_mode & 0o777 == 0o600
    assert not Path(f"{archive}.partial").exists()
