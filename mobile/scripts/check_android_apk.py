"""Verify an existing preview APK. Never signs, edits, installs or publishes it."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class InvalidApk(Exception):
    pass


def require(condition, message):
    if not condition:
        raise InvalidApk(message)


def tool(name):
    found = shutil.which(name)
    if found:
        return found
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk = os.environ.get(variable)
        if sdk:
            candidates = list((Path(sdk) / "build-tools").glob(f"*/{name}"))
            candidates.sort(key=lambda path: tuple(int(n) for n in re.findall(r"\d+", path.parent.name)), reverse=True)
            if candidates:
                return str(candidates[0])
    raise InvalidApk(f"Required Android tool unavailable: {name}")


def run(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        raise InvalidApk("Android verification tool could not complete") from None
    # Tool output may include unexpected APK data. Do not copy it into logs.
    require(result.returncode == 0, f"Android verification tool rejected the APK: {Path(args[0]).name}")
    return result.stdout


def elf_aligned(data):
    require(data[:6] == b"\x7fELF\x02\x01" and len(data) >= 64, "Expected 64-bit little-endian ELF")
    require(struct.unpack_from("<H", data, 18)[0] == 183, "Expected AArch64 native library")
    offset = struct.unpack_from("<Q", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 54)
    require(size >= 56 and count > 0 and offset + count * size <= len(data), "Invalid ELF program headers")
    loads = 0
    for index in range(count):
        start = offset + index * size
        if struct.unpack_from("<I", data, start)[0] != 1:
            continue
        loads += 1
        file_offset, address = struct.unpack_from("<QQ", data, start + 8)
        alignment = struct.unpack_from("<Q", data, start + 48)[0]
        require(alignment >= 16384 and alignment & (alignment - 1) == 0
                and file_offset % alignment == address % alignment, "ELF LOAD segment lacks 16-KiB alignment")
    require(loads > 0, "ELF contains no LOAD segments")


def check_archive(apk, policy):
    with zipfile.ZipFile(apk) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        require(len(names) == len(set(names)), "Duplicate ZIP entry")
        require(sum(item.file_size for item in infos) <= 2_000_000_000, "APK unpacked size exceeds preview limit")
        require(all(item.file_size <= 256_000_000 for item in infos), "APK entry exceeds preview limit")
        require("AndroidManifest.xml" in names, "Android manifest missing")
        require("assets/index.android.bundle" in names, "Standalone JS bundle missing")
        require(archive.getinfo("assets/index.android.bundle").file_size > 0, "Standalone JS bundle empty")
        require(policy["api_origin"].encode() in archive.read("assets/index.android.bundle"), "Expected API origin missing from JS bundle")
        abis = set()
        native_count = 0
        for item in infos:
            path = PurePosixPath(item.filename)
            require(not path.is_absolute() and ".." not in path.parts, "Unsafe ZIP entry path")
            lower = path.name.lower()
            require(not (lower == ".env" or lower.startswith(".env.") or ".git" in path.parts
                         or path.suffix.lower() in {".jks", ".keystore", ".p8", ".p12", ".key", ".pem", ".mobileprovision"}),
                    "Sensitive file type packaged in APK")
            if item.is_dir():
                continue
            data = archive.read(item)
            require(not any(marker in data for marker in (
                b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN RSA PRIVATE KEY-----",
                b"-----BEGIN EC PRIVATE KEY-----", b"-----BEGIN OPENSSH PRIVATE KEY-----",
            )), "Private key marker packaged in APK")
            if len(path.parts) == 3 and path.parts[0] == "lib" and path.suffix == ".so":
                abis.add(path.parts[1])
                elf_aligned(data)
                native_count += 1
        require(abis == set(policy["abis"]) and native_count > 0, "Unexpected native architectures")
    return native_count


def check_metadata(badging, xmltree, signature, policy):
    package = re.search(r"^package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging, re.M)
    require(package is not None, "Package metadata unavailable")
    require(package.groups() == (policy["package"], str(policy["version_code"]), policy["version"]), "Package or version mismatch")
    sdk = re.search(r"^sdkVersion:'(\d+)'", badging, re.M)
    target = re.search(r"^targetSdkVersion:'(\d+)'", badging, re.M)
    require(sdk and int(sdk[1]) == policy["min_sdk"], "Unexpected minimum Android SDK")
    require(target and int(target[1]) >= policy["min_target_sdk"], "Android target SDK too low")
    require("application-debuggable" not in badging, "Debuggable APK rejected")
    permissions = set(re.findall(r"^uses-permission(?:-sdk-\d+)?: name='([^']+)'", badging, re.M))
    require(not permissions.intersection(policy["forbidden_permissions"]), "Forbidden Android permission")
    require(re.search(r"android:allowBackup\([^)]*\)=\(type 0x12\)0x0\b", xmltree), "Android backup must be explicitly disabled")
    require(not re.search(r"android:usesCleartextTraffic\([^)]*\)=\(type 0x12\)0xffffffff\b", xmltree), "Cleartext traffic enabled")
    require("Verified using v2 scheme (APK Signature Scheme v2): true" in signature, "APK v2 signature required")
    certificates = re.findall(r"^(?:Signer #\d+|V\d(?:\.\d+)? Signer:?) certificate SHA-256 digest: ([a-fA-F0-9]+)$", signature, re.M)
    require(re.search(r"^Number of signers: 1$", signature, re.M)
            and {value.lower() for value in certificates} == {policy["certificate_sha256"].lower()}, "Unexpected signing certificate")
    return {"package": package[1], "version": package[3], "version_code": int(package[2]),
            "min_sdk": int(sdk[1]), "target_sdk": int(target[1]), "permissions": sorted(permissions),
            "certificate_sha256": certificates[0].lower()}


def verify(apk, policy):
    signature = run(tool("apksigner"), "verify", "--verbose", "--print-certs", str(apk))
    badging = run(tool("aapt"), "dump", "badging", str(apk))
    xmltree = run(tool("aapt"), "dump", "xmltree", str(apk), "AndroidManifest.xml")
    run(tool("zipalign"), "-c", "-P", "16", "4", str(apk))
    metadata = check_metadata(badging, xmltree, signature, policy)
    native_count = check_archive(apk, policy)
    with apk.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"report_version": 1, "purpose": "preview-only", "verified_at": datetime.now(timezone.utc).isoformat(),
            "artifact": apk.name, "bytes": apk.stat().st_size, "sha256": digest,
            **metadata, "api_origin": policy["api_origin"], "abis": policy["abis"], "native_libraries": native_count,
            "checks": ["apk-signature-v2", "pinned-certificate", "package-version", "permissions-backup",
                       "standalone-js", "expected-api-origin", "zip-alignment-16k", "elf-alignment-16k", "sensitive-file-patterns"],
            "limitations": ["No runtime/device test", "Not store signing", "Pattern scan cannot detect arbitrary embedded secrets",
                            "No source provenance assertion or byte-for-byte reproducibility claim"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--policy", type=Path, default=ROOT / "preview-policy.json")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text())
        require(policy["version"] == json.loads((ROOT / "package.json").read_text())["version"], "Preview policy/package.json version mismatch")
        result = verify(args.apk.resolve(), policy)
        if args.report:
            require(args.report.resolve() != args.apk.resolve(), "Report must not overwrite APK")
            args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (InvalidApk, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        message = str(error) if isinstance(error, InvalidApk) else "APK or verification policy could not be read"
        print("APK check failed: " + message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
