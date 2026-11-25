"""Private object access and malware screening for PDF attachments."""
from contextlib import contextmanager
from fcntl import LOCK_EX, flock
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings

MAX_PDF_BYTES = 10 * 1024**2
MAX_PDF_COUNT = 20
MAX_ACCOUNT_BYTES = 100 * 1024**2
LOCAL_STORE_LIMIT = 1024**3
LOCAL_DISK_RESERVE = 2 * 1024**3


class PdfServiceUnavailable(RuntimeError):
    pass


class InvalidPdf(ValueError):
    pass


@lru_cache(maxsize=4)
def s3_client(endpoint, region, access_key, secret_key):
    return boto3.client(
        "s3", endpoint_url=endpoint, region_name=region, aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(connect_timeout=3, read_timeout=8, retries={"total_max_attempts": 1},
                      s3={"addressing_style": "path"}, request_checksum_calculation="when_required",
                      response_checksum_validation="when_required"),
    )


def s3():
    return s3_client(settings.pdf_s3_endpoint, settings.pdf_s3_region, settings.pdf_s3_access_key.get_secret_value(),
                     settings.pdf_s3_secret_key.get_secret_value())


def object_key(object_id: UUID) -> str:
    return f"teleiosis/pdf/{object_id.hex}.pdf"


@contextmanager
def local_store_lock(directory: Path):
    with (directory / ".write.lock").open("ab") as lock:
        flock(lock.fileno(), LOCK_EX)
        yield


def local_paths(object_id: UUID):
    directory = settings.pdf_local_dir
    return directory / (object_id.hex + ".pdf"), directory / (object_id.hex + ".part")


def put_local_pdf(object_id: UUID, data: bytes):
    target, partial = local_paths(object_id)
    with local_store_lock(target.parent):
        partial.unlink(missing_ok=True)
        stored = sum(path.stat().st_size for path in target.parent.iterdir()
                     if path.suffix in {".pdf", ".part"})
        previous = target.stat().st_size if target.exists() else 0
        if stored - previous + len(data) > LOCAL_STORE_LIMIT:
            raise PdfServiceUnavailable
        if shutil.disk_usage(target.parent).free - len(data) < LOCAL_DISK_RESERVE:
            raise PdfServiceUnavailable
        try:
            with os.fdopen(os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            partial.replace(target)
            fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            partial.unlink(missing_ok=True)


def put_pdf(object_id: UUID, data: bytes) -> None:
    try:
        if settings.pdf_local_dir is not None:
            put_local_pdf(object_id, data)
            return
        s3().put_object(Bucket=settings.pdf_s3_bucket, Key=object_key(object_id), Body=data,
                        ContentLength=len(data), ContentType="application/pdf")
    except (OSError, BotoCoreError, ClientError):
        raise PdfServiceUnavailable from None


def get_pdf(object_id: UUID, expected_size: int) -> bytes:
    try:
        if settings.pdf_local_dir is not None:
            target, _ = local_paths(object_id)
            with target.open("rb") as stream:
                data = stream.read(expected_size + 1)
            if len(data) != expected_size:
                raise PdfServiceUnavailable
            return data
        result = s3().get_object(Bucket=settings.pdf_s3_bucket, Key=object_key(object_id))
        body = result["Body"]
        try:
            if result["ContentLength"] != expected_size:
                raise PdfServiceUnavailable
            data = body.read(expected_size + 1)
            if len(data) != expected_size:
                raise PdfServiceUnavailable
            return data
        finally:
            body.close()
    except (OSError, BotoCoreError, ClientError):
        raise PdfServiceUnavailable from None


def delete_pdf_object(object_id: UUID) -> None:
    try:
        if settings.pdf_local_dir is not None:
            target, partial = local_paths(object_id)
            with local_store_lock(target.parent):
                partial.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
            return
        s3().delete_object(Bucket=settings.pdf_s3_bucket, Key=object_key(object_id))
    except (OSError, BotoCoreError, ClientError):
        raise PdfServiceUnavailable from None


@contextmanager
def scanner_connection():
    if settings.pdf_scanner_socket is None:
        with socket.create_connection((settings.pdf_scanner_host, settings.pdf_scanner_port), timeout=8) as client:
            yield client
    else:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(8)
            client.connect(str(settings.pdf_scanner_socket))
            yield client


def scan_pdf(data: bytes) -> None:
    if not re.match(rb"%PDF-(?:1\.[0-7]|2\.0)[\r\n]", data) or not data.rstrip().endswith(b"%%EOF"):
        raise InvalidPdf("invalid_pdf")
    try:
        with scanner_connection() as client:
            client.sendall(b"zINSTREAM\0" + len(data).to_bytes(4, "big"))
            client.sendall(data)
            client.sendall(bytes(4))
            response = bytearray()
            while len(response) < 512 and not response.endswith(b"\0"):
                chunk = client.recv(512 - len(response))
                if not chunk:
                    break
                response.extend(chunk)
    except OSError:
        raise PdfServiceUnavailable from None
    if response.endswith(b" FOUND\0"):
        raise InvalidPdf("unsafe_pdf")
    if response != b"stream: OK\0":
        raise PdfServiceUnavailable
    try:
        checked = subprocess.run(
            [sys.executable, "-m", "app.pdf_validate"], input=data, timeout=7,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={"PATH": os.defpath},
        )
    except subprocess.TimeoutExpired:
        raise InvalidPdf("unsupported_pdf") from None
    except OSError:
        raise PdfServiceUnavailable from None
    if checked.returncode != 0:
        raise InvalidPdf("unsupported_pdf")


def pdf_character_count(data: bytes) -> int | None:
    """Count text in a previously screened PDF without affecting the ability to save it."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.pdf_validate", "--count-text"], input=data, timeout=3,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={"PATH": os.defpath},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not re.fullmatch(rb"[0-9]{1,10}\n", result.stdout):
        return None
    count = int(result.stdout)
    return count if 0 < count <= 2_147_483_647 else None
