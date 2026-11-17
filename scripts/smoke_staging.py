"""Closed staging smoke, executed on the host; never prints credentials/tokens.

Requires explicit --allow-write and a gateway marked as staging. Creates and
deletes one synthetic account. Reads its test mail from the private capture volume.
"""
import argparse
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from http.cookiejar import CookieJar
import json
from pathlib import Path
import re
import secrets
import socket
import ssl
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPCookieProcessor
import base64


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--ca-file")
    parser.add_argument("--connect-host")
    parser.add_argument("--access-file", default="/srv/teleiosis/deploy/.env.staging-access")
    parser.add_argument("--mail-volume", default="teleiosis-staging_capture_mail")
    parser.add_argument("--allow-write", action="store_true")
    args = parser.parse_args()
    if not args.allow_write:
        raise SystemExit("Explicit --allow-write is required for this synthetic-account smoke.")
    address = urlsplit(args.base_url)
    if address.scheme != "https" or address.username or address.password:
        raise SystemExit("An HTTPS URL without embedded credentials is required.")
    origin = f"https://{address.hostname}"
    if args.connect_host:
        original = socket.getaddrinfo
        def resolve(host, *rest, **kwargs):
            return original(args.connect_host if host == address.hostname else host, *rest, **kwargs)
        socket.getaddrinfo = resolve
    credentials = {}
    for line in Path(args.access_file).read_text().splitlines():
        key, value = line.split(":", 1)
        credentials[key] = value.strip()
    authorization = "Basic " + base64.b64encode(
        f"{credentials['Username']}:{credentials['Password']}".encode()
    ).decode()
    context = ssl.create_default_context(cafile=args.ca_file)
    opener = build_opener(HTTPSHandler(context=context), HTTPCookieProcessor(CookieJar()))

    def request(method, path, body=None, expected=200, auth=True):
        headers = {"Origin": origin}
        if auth:
            headers["Authorization"] = authorization
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        try:
            response = opener.open(Request(args.base_url.rstrip("/") + path, data=data,
                                           headers=headers, method=method), timeout=10)
        except HTTPError as error:
            response = error
        with response:
            if response.status != expected:
                raise RuntimeError(f"Unexpected HTTP status for {method} {path}: {response.status}")
            if auth and response.headers.get("X-Teleiosis-Environment") != "staging":
                raise RuntimeError("Refusing writes: gateway is not marked as staging")
            content = response.read()
            return json.loads(content) if content and "application/json" in response.headers.get("Content-Type", "") else content

    request("GET", "/", expected=401, auth=False)
    request("GET", "/")
    request("GET", "/app/login.html")
    for path in ("/docs", "/redoc", "/openapi.json", "/ready"):
        request("GET", path, expected=404)
    print("HTTPS, gateway authentication, warning and private routes passed.", flush=True)

    mail_dir = Path(subprocess.check_output([
        "docker", "volume", "inspect", args.mail_volume, "--format", "{{.Mountpoint}}"
    ], text=True).strip())
    email = f"staging-smoke-{secrets.token_hex(6)}@example.com"
    password = secrets.token_urlsafe(24)

    def captured(subject_prefix, token_path=None, wait=10):
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            for file in mail_dir.glob("*.eml"):
                message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
                if message["To"] == email and str(message["Subject"]).startswith(subject_prefix):
                    if token_path:
                        match = re.search(re.escape(token_path) + r"#token=([A-Za-z0-9_-]+)", message.get_content())
                        if match:
                            return match.group(1)
                    else:
                        return True
            time.sleep(0.25)
        raise RuntimeError("Expected synthetic email was not captured before the deadline")

    request("POST", "/auth/register", {"email": email, "password": password,
                                       "consent": True, "timezone": "UTC"}, expected=201)
    category = request("POST", "/categories", {"name": "Staging smoke"}, expected=201)
    item = request("POST", "/contents", {"note": "synthetic-staging-smoke", "category_id": category["id"]}, expected=201)
    request("POST", "/auth/email-verification/request", expected=202)
    token = captured("Teleiosis: подтверждение", "/app/verify.html")
    request("POST", "/auth/email-verification/confirm", {"token": token}, expected=204)
    assert request("GET", "/me")["email_verified_at"]
    request("POST", "/auth/password-reset/request", {"email": email}, expected=202)
    token = captured("Teleiosis: восстановление", "/app/reset.html")
    password = secrets.token_urlsafe(24)
    request("POST", "/auth/password-reset/confirm", {"token": token, "password": password}, expected=204)
    request("GET", "/me", expected=401)
    request("POST", "/auth/login", {"email": email, "password": password})
    assert request("GET", "/contents")["total"] == 1
    print("Register, categories, material, private verify/reset mail and session revocation passed.", flush=True)

    now = datetime.now(timezone.utc)
    request("PATCH", f"/contents/{item['id']}", {"status": "planned"})
    request("PATCH", "/me/settings", {"reminders_enabled": True, "reminder_time": now.strftime("%H:%M")})
    request("PUT", f"/contents/{item['id']}/reminder", {"scheduled_at": (now + timedelta(seconds=3)).isoformat()})
    print("Waiting for the real worker to capture reminder and daily digest (up to 75 seconds).", flush=True)
    captured("Teleiosis: напоминание:", wait=75)
    captured("Teleiosis: что изучить сегодня", wait=10)
    request("PATCH", f"/contents/{item['id']}", {"status": "studied"})
    assert request("GET", "/stats")["by_status"]["studied"] == 1
    exported = request("GET", "/me/export")
    assert len(exported["contents"]) == 1
    request("POST", "/auth/delete-account", {"password": password}, expected=204)
    request("GET", "/me", expected=401)
    # Remove this synthetic account's test mail; never delete other test mail.
    for file in mail_dir.glob("*.eml"):
        message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
        if message["To"] == email:
            file.unlink()
    print("Worker reminder/digest, stats, export, account deletion and synthetic-mail cleanup passed.", flush=True)


if __name__ == "__main__":
    main()
