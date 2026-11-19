"""Offline verifier regression. Synthetic ZIPs are not signed Android APKs."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("apk_check", ROOT / "mobile/scripts/check_android_apk.py")
apk_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apk_check)


def elf(alignment=16384):
    data = bytearray(120)
    data[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", data, 18, 183)
    struct.pack_into("<Q", data, 32, 64)
    struct.pack_into("<HH", data, 54, 56, 1)
    struct.pack_into("<I", data, 64, 1)
    struct.pack_into("<Q", data, 112, alignment)
    return bytes(data)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "mobile/preview-policy.json").read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.apk = Path(self.temp.name) / "fixture.apk"
        self.badging = (
            f"package: name='{self.policy['package']}' versionCode='{self.policy['version_code']}' versionName='{self.policy['version']}'\n"
            "sdkVersion:'24'\ntargetSdkVersion:'36'\nuses-permission: name='android.permission.INTERNET'\n"
        )
        self.xml = "A: android:allowBackup(0x01010280)=(type 0x12)0x0\n"
        self.signature = "Verified using v2 scheme (APK Signature Scheme v2): true\nNumber of signers: 1\nSigner #1 certificate SHA-256 digest: " + self.policy["certificate_sha256"] + "\n"

    def archive(self, additions=(), bundle=True, origin=True, abi="arm64-v8a", native=None):
        with zipfile.ZipFile(self.apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", b"synthetic-manifest")
            if bundle:
                archive.writestr("assets/index.android.bundle", b"synthetic-js" + (self.policy["api_origin"].encode() if origin else b""))
            archive.writestr(f"lib/{abi}/libsynthetic.so", elf() if native is None else native)
            for name, content in additions:
                archive.writestr(name, content)

    def test_valid_archive(self):
        self.archive()
        self.assertEqual(apk_check.check_archive(self.apk, self.policy), 1)

    def test_metadata_matches_policy(self):
        result = apk_check.check_metadata(self.badging, self.xml, self.signature, self.policy)
        self.assertEqual(result["certificate_sha256"], self.policy["certificate_sha256"])
        result = apk_check.check_metadata(self.badging, self.xml, self.signature.replace("Signer #1", "V2 Signer:"), self.policy)
        self.assertEqual(result["certificate_sha256"], self.policy["certificate_sha256"])

    def test_rejects_wrong_or_unsigned_certificate(self):
        for signature in ("", self.signature.replace(self.policy["certificate_sha256"], "0" * 64),
                          self.signature.replace("true", "false"), self.signature + "Signer #2 certificate SHA-256 digest: " + "f" * 64 + "\n"):
            with self.subTest(signature=signature), self.assertRaises(apk_check.InvalidApk):
                apk_check.check_metadata(self.badging, self.xml, signature, self.policy)

    def test_rejects_wrong_package_version_sdk_and_debuggable(self):
        for badging in (self.badging.replace(self.policy["package"], "other.package"),
                        self.badging.replace(f"versionCode='{self.policy['version_code']}'", "versionCode='0'"),
                        self.badging.replace("sdkVersion:'24'", "sdkVersion:'23'"),
                        self.badging.replace("targetSdkVersion:'36'", "targetSdkVersion:'28'"),
                        self.badging + "application-debuggable\n"):
            with self.subTest(badging=badging), self.assertRaises(apk_check.InvalidApk):
                apk_check.check_metadata(badging, self.xml, self.signature, self.policy)

    def test_rejects_forbidden_permissions_and_backup(self):
        for permission in self.policy["forbidden_permissions"]:
            with self.subTest(permission=permission), self.assertRaises(apk_check.InvalidApk):
                apk_check.check_metadata(self.badging + f"uses-permission: name='{permission}'\n", self.xml, self.signature, self.policy)
        for xml in ("", self.xml.replace("0x0\n", "0xffffffff\n"), self.xml + "A: android:usesCleartextTraffic(0x010104ec)=(type 0x12)0xffffffff\n"):
            with self.subTest(xml=xml), self.assertRaises(apk_check.InvalidApk):
                apk_check.check_metadata(self.badging, xml, self.signature, self.policy)

    def test_rejects_missing_js_and_wrong_abi(self):
        for options in ({"bundle": False}, {"origin": False}, {"abi": "x86_64"}):
            self.archive(**options)
            with self.assertRaises(apk_check.InvalidApk):
                apk_check.check_archive(self.apk, self.policy)

    def test_rejects_keys_env_and_traversal_without_printing_content(self):
        for name, data in (("assets/.env.production", b"synthetic-secret"),
                           ("assets/key.p8", b"synthetic-secret"),
                           ("assets/opaque", b"-----BEGIN PRIVATE KEY-----synthetic-secret"),
                           ("../escape", b"synthetic-secret")):
            self.archive([(name, data)])
            with self.subTest(name=name), self.assertRaises(apk_check.InvalidApk) as context:
                apk_check.check_archive(self.apk, self.policy)
            self.assertNotIn("synthetic-secret", str(context.exception))

    def test_rejects_unaligned_and_truncated_elf(self):
        for native in (elf(4096), elf(32767), b"invalid", elf()[:100]):
            self.archive(native=native)
            with self.subTest(native=native), self.assertRaises(apk_check.InvalidApk):
                apk_check.check_archive(self.apk, self.policy)


if __name__ == "__main__":
    unittest.main()
