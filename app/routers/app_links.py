"""Verified HTTPS email links retain the existing web fallback."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings

router = APIRouter(tags=["app-links"])


@router.get("/.well-known/assetlinks.json", include_in_schema=False)
def android_app_links():
    if not settings.mobile_android_cert_sha256:
        raise HTTPException(404, "App links not configured")
    return JSONResponse([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {"namespace": "android_app", "package_name": settings.mobile_application_id,
                   "sha256_cert_fingerprints": settings.mobile_android_cert_sha256},
    }], headers={"Cache-Control": "public, max-age=300"})


@router.get("/.well-known/apple-app-site-association", include_in_schema=False)
def ios_app_links():
    if not settings.mobile_apple_team_id:
        raise HTTPException(404, "App links not configured")
    return JSONResponse({"applinks": {"apps": [], "details": [{
        "appID": f"{settings.mobile_apple_team_id}.{settings.mobile_application_id}",
        "paths": ["/app/reset.html", "/app/verify.html"],
    }]}}, headers={"Cache-Control": "public, max-age=300"})
