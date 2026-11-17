"""Private/public staging auth smoke with synthetic data and no credential output."""
import argparse
import base64
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
from urllib.request import HTTPRedirectHandler, HTTPSHandler, HTTPCookieProcessor, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--ca-file")
    parser.add_argument("--connect-host")
    parser.add_argument("--access-file", default="/srv/teleiosis/deploy/.env.staging-access")
    parser.add_argument("--mail-volume", default="teleiosis-staging_capture_mail")
    parser.add_argument("--allow-write", action="store_true")
    args = parser.parse_args()
    address = urlsplit(args.base_url)
    if not args.allow_write or address.scheme != "https" or address.username or address.password or address.path not in ("", "/") or address.query or address.fragment:
        raise SystemExit("Explicit --allow-write and an HTTPS origin without credentials are required")
    if args.connect_host:
        original_resolve = socket.getaddrinfo
        socket.getaddrinfo = lambda host, *rest, **kwargs: original_resolve(args.connect_host if host == address.hostname else host, *rest, **kwargs)
    access = dict(line.split(":", 1) for line in Path(args.access_file).read_text().splitlines() if line.strip())
    gate = "Basic " + base64.b64encode(f"{access['Username'].strip()}:{access['Password'].strip()}".encode()).decode()
    context = ssl.create_default_context(cafile=args.ca_file)
    native = build_opener(HTTPSHandler(context=context), NoRedirect())
    cookies = CookieJar()
    browser = build_opener(HTTPSHandler(context=context), HTTPCookieProcessor(cookies), NoRedirect())

    def request(method, path, body=None, token=None, web=False, expected=200, extra=None):
        headers = {"Authorization": gate, "Origin": f"https://{address.hostname}"} if web else {"X-Staging-Authorization": gate}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if extra:
            headers.update(extra)
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        try:
            response = (browser if web else native).open(Request(args.base_url.rstrip("/") + path, data=data, headers=headers, method=method), timeout=15)
        except HTTPError as error:
            response = error
        with response:
            if response.status != expected:
                raise RuntimeError(f"Unexpected status for {method} {path}: {response.status}")
            if response.headers.get("X-Teleiosis-Environment") != "staging":
                raise RuntimeError("Refusing writes: missing staging marker")
            if not web:
                assert "Set-Cookie" not in response.headers, "Native API changed browser credentials"
                assert response.headers.get("Cache-Control") == "no-store"
            content = response.read()
            return json.loads(content) if content and "application/json" in response.headers.get("Content-Type", "") else None

    request("GET", "/", web=True)  # Read-only preflight before any write.
    mail_dir = Path(subprocess.check_output(["docker", "volume", "inspect", args.mail_volume, "--format", "{{.Mountpoint}}"], text=True).strip())
    email = f"mobile-smoke-{secrets.token_hex(8)}@example.com"
    old_password, new_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)

    def captured(path):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            for file in mail_dir.glob("*.eml"):
                message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
                if message["To"] == email:
                    match = re.search(re.escape(path) + r"#token=([A-Za-z0-9_-]{16,128})", message.get_content())
                    if match:
                        return match.group(1)
            time.sleep(0.2)
        raise RuntimeError("Synthetic email was not captured")

    try:
        issued = request("POST", "/mobile/auth/register", {"email": email, "password": old_password, "consent": True}, expected=201)
        token = issued["token"]
        assert issued["token_type"] == "Bearer"
        assert request("GET", "/mobile/auth/session", token=token)["user"]["email"] == email
        request("GET", "/me", web=True, extra={"Cookie": f"__Host-session={token}"}, expected=401)
        request("POST", "/auth/login", {"email": email, "password": old_password}, web=True)
        cookie = next(cookie for cookie in cookies if cookie.name == "__Host-session")
        request("GET", "/mobile/auth/session", token=cookie.value, expected=401)
        request("GET", "/mobile/auth/session", token=token, extra={"Cookie": f"{cookie.name}={cookie.value}"}, expected=401)
        request("POST", "/mobile/auth/email-verification/request", {}, token=token, expected=202)
        verify = captured("/app/verify.html")
        request("POST", "/mobile/auth/email-verification/confirm", {"token": verify}, expected=204)
        assert request("GET", "/mobile/auth/session", token=token)["user"]["email_verified_at"]
        request("POST", "/mobile/auth/password-reset/request", {"email": email}, expected=202)
        reset = captured("/app/reset.html")
        request("POST", "/mobile/auth/password-reset/confirm", {"token": reset, "password": new_password}, expected=204)
        request("GET", "/mobile/auth/session", token=token, expected=401)
        request("GET", "/me", web=True, expected=401)
        request("POST", "/mobile/auth/password-reset/confirm", {"token": reset, "password": new_password}, expected=400)
        token = request("POST", "/mobile/auth/login", {"email": email, "password": new_password})["token"]
        request("POST", "/mobile/auth/logout", {}, token=token, expected=204)
        request("GET", "/mobile/auth/session", token=token, expected=401)
        print("Mobile HTTPS auth: registration/login, cookie isolation, mixed rejection, captured verify/reset, global revocation and logout passed", flush=True)
    finally:
        deleted = False
        for password in (new_password, old_password):
            try:
                request("POST", "/auth/login", {"email": email, "password": password}, web=True)
                request("POST", "/auth/delete-account", {"password": password}, web=True, expected=204)
                deleted = True
                break
            except (RuntimeError, OSError):
                pass
        if deleted:
            for file in mail_dir.glob("*.eml"):
                if BytesParser(policy=policy.default).parsebytes(file.read_bytes())["To"] == email:
                    file.unlink()
            print("Synthetic account and its captured email removed", flush=True)
        else:
            raise RuntimeError("Synthetic cleanup not confirmed; inspect private staging")


if __name__ == "__main__":
    main()
