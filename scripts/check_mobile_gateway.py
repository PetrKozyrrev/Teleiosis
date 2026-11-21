"""Exercise the real staging Caddy transport with synthetic credentials and TLS.

Requires Docker and a Python application image. No host ports, live DB or
deployment changes. Disposable internal CA and resources are removed afterward.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4


def docker(*args, check=True):
    return subprocess.run(["docker", *args], check=check, text=True, capture_output=True, timeout=180).stdout.strip()


ECHO = '''
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data=json.dumps({"auth":self.headers.get("Authorization"),"gate":self.headers.get("X-Staging-Authorization"),
                         "cookie":self.headers.get("Cookie"),"path":self.path,"method":self.command}).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    do_POST=do_GET
    do_PUT=do_GET
    do_PATCH=do_GET
    do_DELETE=do_GET
    def log_message(self,*args): pass
HTTPServer(("0.0.0.0",8000),Handler).serve_forever()
'''

CLIENT = '''
import base64,http.client,json,ssl,time
from pathlib import Path
root=Path("/ca/caddy/pki/authorities/local/root.crt")
for _ in range(30):
    if root.exists(): break
    time.sleep(0.2)
ctx=ssl.create_default_context(cafile=str(root))
good="Basic "+base64.b64encode(b"tester:synthetic-gateway-only").decode()
bad="Basic "+base64.b64encode(b"tester:incorrect").decode()
def request(path,headers=None,method="GET"):
    connection=http.client.HTTPSConnection("mobile-probe.localhost",443,context=ctx,timeout=10)
    connection.request(method,path,headers=headers or {})
    response=connection.getresponse()
    result=(response.status,dict((k.lower(),v) for k,v in response.getheaders()),response.read())
    connection.close()
    return result
for headers in ({},{"Authorization":"Bearer synthetic-session-token"},{"X-Staging-Authorization":bad}):
    status,headers,body=request("/mobile/auth/session",headers)
    assert status==401 and headers.get("www-authenticate","").lower().startswith("basic"), "Gateway bypass"
status,headers,body=request("/mobile/auth/register",{"X-Staging-Authorization":good})
assert status==200 and all(json.loads(body)[key] is None for key in ("auth","gate")), "Gateway credential leaked to anonymous API"
status,headers,body=request("/mobile/auth/session",{"X-Staging-Authorization":good,"Authorization":"Bearer synthetic-session-token"})
assert status==200 and json.loads(body)["auth"]=="Bearer synthetic-session-token" and json.loads(body)["gate"] is None, "Bearer was lost or gateway credential leaked"
assert headers.get("x-teleiosis-environment")=="staging"
for method,path in (("GET","/mobile/library/tags"),("POST","/mobile/library/tags"),
                    ("PATCH","/mobile/library/tags/12"),("DELETE","/mobile/library/tags/12"),
                    ("GET","/mobile/library/collections"),("POST","/mobile/library/collections"),
                    ("PATCH","/mobile/library/collections/12"),("DELETE","/mobile/library/collections/12"),
                    ("POST","/mobile/library/imports/preview"),("POST","/mobile/library/imports/apply"),
                    ("GET","/mobile/library/search?q=sample&search_in=all"),
                    ("GET","/mobile/library/pdf"),("POST","/mobile/library/pdf?category_id=3"),
                    ("GET","/mobile/library/contents/12/pdf"),("GET","/mobile/library/contents/12/pdf/download"),
                    ("GET","/mobile/library/contents/12/organization"),("PATCH","/mobile/library/contents/12/organization")):
    assert request(path,{"Authorization":"Bearer synthetic-session-token"},method)[0]==401
    assert request(path,{"X-Staging-Authorization":bad},method)[0]==401
    status,headers,body=request(path,{"X-Staging-Authorization":good,"Authorization":"Bearer synthetic-session-token"},method)
    assert status==200 and json.loads(body)=={"auth":"Bearer synthetic-session-token","gate":None,"cookie":None,"path":path,"method":method}
    assert headers.get("cache-control")=="no-store"
status,headers,body=request("/me",{"Authorization":good})
assert status==200 and all(json.loads(body)[key] is None for key in ("auth","gate")), "Browser transport regression"
cookie="session=synthetic-web-cookie"
status,headers,body=request("/mobile/auth/session",{"X-Staging-Authorization":good,"Authorization":"Bearer synthetic-session-token","Cookie":cookie})
assert status==200 and json.loads(body)["cookie"]==cookie, "API must see mixed credentials on the existing mobile auth routes"
for method,path in (("GET","/contents?q=sample"),("POST","/contents"),("POST","/contents/submissions"),("GET","/contents/12"),
                    ("PATCH","/contents/12"),("DELETE","/contents/12"),("POST","/contents/12/open"),
                    ("PATCH","/contents/12/versioned"), ("GET","/contents/12/reminder"), ("PUT","/contents/12/reminder"),
                    ("DELETE","/contents/12/reminder"), ("GET","/me"), ("PATCH","/me/settings"), ("GET","/me/export"),
                    ("GET","/stats"), ("POST","/auth/change-password"), ("POST","/auth/delete-account"),
                    ("GET","/categories"),("POST","/categories"),("PATCH","/categories/12"),("DELETE","/categories/12")):
    assert request(path,{"Authorization":"Bearer synthetic-session-token"},method)[0]==401
    assert request(path,{"X-Staging-Authorization":bad},method)[0]==401
    status,headers,body=request(path,{"X-Staging-Authorization":good,"Authorization":"Bearer synthetic-session-token","Cookie":cookie},method)
    assert status==200 and json.loads(body)=={"auth":"Bearer synthetic-session-token","gate":None,"cookie":None,"path":path,"method":method}
    assert headers.get("cache-control")=="no-store"
    status,headers,body=request(path,{"Authorization":good,"Cookie":cookie},method)
    assert status==200 and json.loads(body)=={"auth":None,"gate":None,"cookie":cookie,"path":path,"method":method}
status,headers,body=request("/contents",{"X-Staging-Authorization":good,"Authorization":good})
assert status==200 and json.loads(body)["auth"] is None, "Basic credential passed as app authorization"
for path in ("/contents/12/unknown","/categories-extra","/auth/unknown","/app/"):
    assert request(path,{"X-Staging-Authorization":good})[0]==401, "Native matcher too broad"
for path in ("/docs","/openapi.json","/ready"):
    assert request(path)[0]==404, "Private API path exposed"
for path in ("/.well-known/assetlinks.json","/.well-known/apple-app-site-association"):
    status,headers,body=request(path)
    assert status==200 and all(json.loads(body)[key] is None for key in ("auth","gate")), "Association metadata requires gateway"
assert request("/.well-known/private.json")[0]==401, "Association bypass too broad"
print("Staging gateway: verified TLS, auth and library header isolation, browser cookies, association metadata and private paths passed")
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="teleiosis:ci")
    parser.add_argument("--caddy-image", default="caddy:2")
    args = parser.parse_args()
    name = "teleiosis-mobile-gw-" + uuid4().hex[:12]
    volume = name + "-ca"
    with tempfile.TemporaryDirectory(prefix="teleiosis-gw-") as temp:
        work = Path(temp)
        work.chmod(0o755)
        caddy = (Path(__file__).resolve().parents[1] / "deploy/Caddyfile.staging").read_text()
        caddy = caddy.replace("admin off", "admin off\n\tlocal_certs\n\tskip_install_trust", 1)
        for filename, contents in (("Caddyfile", caddy), ("echo.py", ECHO), ("client.py", CLIENT)):
            (work / filename).write_text(contents)
            (work / filename).chmod(0o644)
        try:
            docker("network", "create", "--internal", name)
            docker("volume", "create", volume)
            hashed = docker("run", "--rm", "--network", "none", args.caddy_image, "caddy", "hash-password", "--algorithm", "argon2id", "--plaintext", "synthetic-gateway-only")
            docker("run", "-d", "--name", name + "-api", "--network", name, "--network-alias", "api", "--read-only", "--tmpfs", "/tmp", "-v", f"{work}:/work:ro", "--entrypoint", "python", args.image, "/work/echo.py")
            docker("run", "-d", "--name", name + "-proxy", "--network", name, "--network-alias", "mobile-probe.localhost", "-e", "DOMAIN=mobile-probe.localhost", "-e", "STAGING_AUTH_HASH=" + hashed, "-v", f"{work / 'Caddyfile'}:/etc/caddy/Caddyfile:ro", "-v", f"{volume}:/data", args.caddy_image)
            print(docker("run", "--rm", "--user", "0", "--network", name, "--read-only", "--tmpfs", "/tmp", "-v", f"{work}:/work:ro", "-v", f"{volume}:/ca:ro", "--entrypoint", "python", args.image, "/work/client.py"))
        finally:
            for suffix in ("-proxy", "-api"):
                docker("rm", "-f", name + suffix, check=False)
            docker("volume", "rm", volume, check=False)
            docker("network", "rm", name, check=False)


if __name__ == "__main__":
    main()
