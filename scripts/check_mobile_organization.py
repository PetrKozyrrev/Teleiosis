"""Disposable HTTPS/API/web regression for block 9A, with synthetic accounts.

Uses an existing Python app image as a dependency runtime, read-only current
sources and an isolated PostgreSQL. No host ports, real env files or staging.
"""
import argparse
from pathlib import Path
import tempfile
import time
from uuid import uuid4

from check_mobile_gateway import docker

CLIENT = r'''
import base64
import http.client
import json
from pathlib import Path
import ssl
import time
from uuid import uuid4

origin = "https://mobile-probe.localhost"
gate = "Basic " + base64.b64encode(b"tester:synthetic-gateway-only").decode()
certificate = Path("/ca/caddy/pki/authorities/local/root.crt")
for attempt in range(120):
    if certificate.exists():
        break
    time.sleep(0.25)
context = ssl.create_default_context(cafile=str(certificate))

def request(path, method="GET", body=None, token=None, web_cookie=None, origin_header=None):
    headers = {"Accept": "application/json"}
    if web_cookie is not None or path == "/auth/login":
        headers["Authorization"] = gate
        if web_cookie:
            headers["Cookie"] = web_cookie
    else:
        headers["X-Staging-Authorization"] = gate
        if token:
            headers["Authorization"] = "Bearer " + token
    if origin_header is not None:
        headers["Origin"] = origin_header
    if body is not None:
        headers["Content-Type"] = "application/json"
    if method == "PATCH" and path.endswith("/organization"):
        headers["If-Match"] = '"' + str(body.pop("_version")) + '"'
    connection = http.client.HTTPSConnection("mobile-probe.localhost", context=context, timeout=30)
    try:
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        value = json.loads(raw) if raw and "application/json" in response.getheader("Content-Type", "") else None
        return response.status, value, dict((key.lower(), value) for key, value in response.getheaders())
    finally:
        connection.close()

for attempt in range(120):
    try:
        if request("/mobile/auth/session")[0] == 401:
            break
    except (OSError, ssl.SSLError):
        pass
    time.sleep(0.25)
else:
    raise AssertionError("Disposable API/proxy did not become ready")
accounts = []
for name in ("a", "b"):
    status, issued, headers = request("/mobile/auth/register", "POST", {
        "email": "org-" + name + "@example.com", "password": "synthetic-test-password", "consent": True,
    })
    assert status == 201, ("register", status)
    accounts.append(issued["token"])
a, b = accounts
status, tag, _ = request("/mobile/library/tags", "POST", {"name": "Тема"}, a)
assert status == 201
status, collection, _ = request("/mobile/library/collections", "POST", {"name": "Подборка"}, a)
assert status == 201
status, item, _ = request("/contents", "POST", {"note": "Синтетическая заметка", "title": "Проверка 9А"}, a)
assert status == 201
path = "/mobile/library/contents/" + str(item["id"]) + "/organization"
status, assigned, _ = request(path, "PATCH", {"tag_ids": [tag["id"]], "collection_ids": [collection["id"]], "_version": 1}, a)
assert status == 200 and assigned["version"] == 2
query = "/contents?tag_id=" + str(tag["id"]) + "&collection_id=" + str(collection["id"]) + "&limit=1"
status, page, _ = request(query, token=a)
assert status == 200 and page["total"] == 1 and page["items"][0]["id"] == item["id"]
assert request(query, token=b)[1]["total"] == 0
assert request(path, token=b)[0] == 404
assert request(path, "PATCH", {"tag_ids": [tag["id"]], "_version": 2}, b)[0] == 404
assert request("/mobile/library/tags/" + str(tag["id"]), "PATCH", {"name": "Переименовано"}, a)[0] == 200
status, data, _ = request("/me/export", token=a)
assert status == 200 and data["tags"][0]["name"] == "Переименовано" and len(data["organization"]) == 2
assert request("/mobile/library/tags", token=b)[1] == []
status, _, headers = request("/auth/login", "POST", {"email": "org-a@example.com", "password": "synthetic-test-password"}, origin_header=origin)
assert status == 200
cookie = headers["set-cookie"].split(";", 1)[0]
assert request("/app/", web_cookie=cookie)[0] == 200
content_path = "/contents/" + str(item["id"])
assert request(content_path, web_cookie=cookie)[1]["title"] == "Проверка 9А"
assert request(content_path, "PATCH", {"title": "Changed via web"}, web_cookie=cookie, origin_header="https://evil.example.com")[0] == 403
assert request(content_path, "PATCH", {"title": "Changed via web"}, web_cookie=cookie, origin_header=origin)[0] == 200
assert request(content_path, token=a)[1]["title"] == "Changed via web"
assert request(path, "PATCH", {"tag_ids": [], "_version": 2}, a)[0] == 412
assert request("/mobile/library/tags/" + str(tag["id"]), "DELETE", token=a)[0] == 204
remaining = request(path, token=a)[1]
assert remaining["tags"] == [] and len(remaining["collections"]) == 1 and remaining["version"] == 4
assert request(content_path, token=a)[0] == 200
assert request(content_path, "DELETE", token=a)[0] == 204
assert request("/mobile/library/collections", token=a)[1][0]["contents_count"] == 0
print("HTTPS organization E2E passed: save/assign/filter/rename/export, two-account isolation, web cookie/CSRF, versions and non-destructive group deletion")
'''

IMPORT_SEARCH = r'''
from urllib.parse import quote

imports = "/mobile/library/imports/"
query = "?q=" + quote("Синтетическая")
search = "/mobile/library/search" + query + "&search_in=note"
assert request(search, token=b)[1]["total"] == 0
assert request(imports + "apply", "POST", data)[0] == 401
status, preview, headers = request(imports + "preview", "POST", data, b)
assert status == 200 and preview["materials"] == 1 and preview["memberships"] == 2
assert headers.get("cache-control") == "no-store"
assert request(search, token=b)[1]["total"] == 0
assert request(imports + "apply", "POST", data, b)[1] == preview
assert request(imports + "apply", "POST", data, b)[1] == dict(preview, replayed=True)
assert request(search, token=a)[1]["total"] == 0
assert request(search, token=b)[1]["total"] == 1
assert request("/contents" + query, token=b)[1]["total"] == 0
assert request("/mobile/auth/logout", "POST", {}, b)[0] == 204
assert request(search, token=b)[0] == 401
print("HTTPS import and search E2E passed: archived library, atomic apply, replay, extended fields, isolation and revoked session")
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Existing project Python image (dependencies must match requirements.txt)")
    parser.add_argument("--image-only", action="store_true", help="Test code copied into the built image instead of mounting working tree sources")
    parser.add_argument("--import-search", action="store_true", help="Also test the block 9B import and extended search")
    parser.add_argument("--caddy-image", default="caddy:2-alpine")
    parser.add_argument("--postgres-image", default="postgres:16")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    docker("run", "--rm", "--network", "none", "-v", f"{root / 'requirements.txt'}:/work/requirements.txt:ro",
           "--entrypoint", "python", args.image, "-c",
           "from importlib.metadata import version; from pathlib import Path; "
           "requirements=[line.split('==') for line in Path('/work/requirements.txt').read_text().splitlines() if line and not line.startswith('#')]; "
           "assert all(version(name)==pinned for name,pinned in requirements), 'Runtime image must match requirements.txt'")
    name = "teleiosis-org-check-" + uuid4().hex[:12]
    volume = name + "-ca"
    with tempfile.TemporaryDirectory(prefix="teleiosis-org-") as temp:
        work = Path(temp)
        work.chmod(0o755)
        caddy = (root / "deploy/Caddyfile.staging").read_text().replace(
            "admin off", "admin off\n\tlocal_certs\n\tskip_install_trust", 1)
        (work / "Caddyfile").write_text(caddy)
        (work / "client.py").write_text(CLIENT + (IMPORT_SEARCH if args.import_search else ""))
        for path in work.iterdir():
            path.chmod(0o644)
        mounts = []
        for part in (() if args.image_only else ("app", "web", "migrations", "alembic.ini")):
            mounts += ["-v", f"{root / part}:/srv/teleiosis/{part}:ro"]
        environment = ["-e", "APP_ENV=dev", "-e", "APP_ORIGIN=https://mobile-probe.localhost",
                       "-e", "EMAIL_BACKEND=console", "-e", "SECRET_KEY=synthetic-only-signing-key-for-local-organization-tests",
                       "-e", "DATABASE_URL=postgresql+psycopg://organization:synthetic-local-only@db:5432/organization"]
        try:
            docker("network", "create", "--internal", name)
            docker("volume", "create", volume)
            docker("run", "-d", "--name", name + "-db", "--network", name, "--network-alias", "db",
                   "-e", "POSTGRES_USER=organization", "-e", "POSTGRES_PASSWORD=synthetic-local-only",
                   "-e", "POSTGRES_DB=organization", "--tmpfs", "/var/lib/postgresql/data", args.postgres_image)
            for attempt in range(60):
                if "accepting connections" in docker("exec", name + "-db", "pg_isready", "-U", "organization", check=False):
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Disposable PostgreSQL did not start")
            docker("run", "--rm", "--network", name, *environment, *mounts, "--entrypoint", "python",
                   args.image, "-m", "alembic", "upgrade", "head")
            docker("run", "-d", "--name", name + "-api", "--network", name, "--network-alias", "api",
                   "--read-only", "--tmpfs", "/tmp", *environment, *mounts, "--entrypoint", "python",
                   args.image, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log")
            hashed = docker("run", "--rm", "--network", "none", args.caddy_image, "caddy", "hash-password",
                            "--algorithm", "argon2id", "--plaintext", "synthetic-gateway-only")
            docker("run", "-d", "--name", name + "-proxy", "--network", name, "--network-alias", "mobile-probe.localhost",
                   "-e", "DOMAIN=mobile-probe.localhost", "-e", "STAGING_AUTH_HASH=" + hashed,
                   "-v", f"{work / 'Caddyfile'}:/etc/caddy/Caddyfile:ro", "-v", f"{volume}:/data", args.caddy_image)
            print(docker("run", "--rm", "--user", "0", "--network", name, "--read-only", "--tmpfs", "/tmp",
                         "-v", f"{work}:/work:ro", "-v", f"{volume}:/ca:ro", "--entrypoint", "python", args.image, "/work/client.py"))
        finally:
            for suffix in ("-proxy", "-api", "-db"):
                docker("rm", "-f", name + suffix, check=False)
            docker("volume", "rm", volume, check=False)
            docker("network", "rm", name, check=False)


if __name__ == "__main__":
    main()
