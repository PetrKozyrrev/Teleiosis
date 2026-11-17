from app.config import settings


def test_unconfigured_domains_do_not_claim_app_association(client, monkeypatch):
    monkeypatch.setattr(settings, "mobile_android_cert_sha256", [])
    monkeypatch.setattr(settings, "mobile_apple_team_id", "")
    assert client.get("/.well-known/assetlinks.json").status_code == 404
    assert client.get("/.well-known/apple-app-site-association").status_code == 404


def test_configured_android_fingerprint_and_ios_paths(client, monkeypatch):
    fingerprint = ":".join(["AB"] * 32)
    monkeypatch.setattr(settings, "mobile_android_cert_sha256", [fingerprint])
    monkeypatch.setattr(settings, "mobile_apple_team_id", "AB12345678")
    android = client.get("/.well-known/assetlinks.json")
    assert android.status_code == 200
    assert android.json()[0]["target"]["sha256_cert_fingerprints"] == [fingerprint]
    ios = client.get("/.well-known/apple-app-site-association")
    assert ios.json()["applinks"]["details"][0]["paths"] == ["/app/reset.html", "/app/verify.html"]
    # Both existing browser fallback pages still load.
    assert client.get("/app/reset.html").status_code == 200
    assert client.get("/app/verify.html").status_code == 200
