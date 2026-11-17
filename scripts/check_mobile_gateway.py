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
        data=json.dumps({"auth":self.headers.get("Authorization"),"gate":self.headers.get("X-Staging-Authorization")}).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    do_POST=do_GET
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
def request(path,headers=None):
    connection=http.client.HTTPSConnection("mobile-probe.localhost",443,context=ctx,timeout=10)
    connection.request("GET",path,headers=headers or {})
    response=connection.getresponse()
    result=(response.status,dict((k.lower(),v) for k,v in response.getheaders()),response.read())
    connection.close()
    return result
for headers in ({},{"Authorization":"Bearer synthetic-session-token"},{"X-Staging-Authorization":bad}):
    status,headers,body=request("/mobile/auth/session",headers)
    assert status==401 and headers.get("www-authenticate","").lower().startswith("basic"), "Gateway bypass"
status,headers,body=request("/mobile/auth/register",{"X-Staging-Authorization":good})
assert status==200 and json.loads(body)=={"auth":None,"gate":None}, "Gateway credential leaked to anonymous API"
status,headers,body=request("/mobile/auth/session",{"X-Staging-Authorization":good,"Authorization":"Bearer synthetic-session-token"})
assert status==200 and json.loads(body)=={"auth":"Bearer synthetic-session-token","gate":None}, "Bearer was lost or gateway credential leaked"
assert headers.get("x-teleiosis-environment")=="staging"
status,headers,body=request("/me",{"Authorization":good})
assert status==200 and json.loads(body)=={"auth":None,"gate":None}, "Browser transport regression"
for path in ("/docs","/openapi.json","/ready"):
    assert request(path)[0]==404, "Private API path exposed"
for path in ("/.well-known/assetlinks.json","/.well-known/apple-app-site-association"):
    status,headers,body=request(path)
    assert status==200 and json.loads(body)=={"auth":None,"gate":None}, "Association metadata requires gateway"
assert request("/.well-known/private.json")[0]==401, "Association bypass too broad"
print("Staging gateway: verified TLS, Basic/Bearer isolation, anonymous auth, browser compatibility, association metadata and private paths passed")
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="teleiosis:ci")
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
            hashed = docker("run", "--rm", "--network", "none", "caddy:2", "caddy", "hash-password", "--algorithm", "argon2id", "--plaintext", "synthetic-gateway-only")
            docker("run", "-d", "--name", name + "-api", "--network", name, "--network-alias", "api", "--read-only", "--tmpfs", "/tmp", "-v", f"{work}:/work:ro", "--entrypoint", "python", args.image, "/work/echo.py")
            docker("run", "-d", "--name", name + "-proxy", "--network", name, "--network-alias", "mobile-probe.localhost", "-e", "DOMAIN=mobile-probe.localhost", "-e", "STAGING_AUTH_HASH=" + hashed, "-v", f"{work / 'Caddyfile'}:/etc/caddy/Caddyfile:ro", "-v", f"{volume}:/data", "caddy:2")
            print(docker("run", "--rm", "--user", "0", "--network", name, "--read-only", "--tmpfs", "/tmp", "-v", f"{work}:/work:ro", "-v", f"{volume}:/ca:ro", "--entrypoint", "python", args.image, "/work/client.py"))
        finally:
            for suffix in ("-proxy", "-api"):
                docker("rm", "-f", name + suffix, check=False)
            docker("volume", "rm", volume, check=False)
            docker("network", "rm", name, check=False)


if __name__ == "__main__":
    main()
