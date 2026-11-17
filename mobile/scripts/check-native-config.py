"""Check generated native safety boundaries; no SDK/device or third-party Python libs."""
from pathlib import Path
import argparse
import plistlib
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument("--ios-share-probe", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
android = "{http://schemas.android.com/apk/res/android}"
tools = "{http://schemas.android.com/tools}"
manifest = ET.parse(root / "android/app/src/main/AndroidManifest.xml").getroot()
app = manifest.find("application")
assert app is not None
assert app.get(android + "fullBackupContent") == "@xml/secure_store_backup_rules"
assert app.get(android + "dataExtractionRules") == "@xml/secure_store_data_extraction_rules"
removed = {p.get(android + "name") for p in manifest.findall("uses-permission") if p.get(tools + "node") == "remove"}
assert {
    "android.permission.RECORD_AUDIO", "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.WRITE_EXTERNAL_STORAGE", "android.permission.READ_MEDIA_IMAGES",
    "android.permission.READ_MEDIA_VIDEO",
} <= removed
intents = app.findall("activity/intent-filter")
single = [i for i in intents if any(a.get(android + "name") == "android.intent.action.SEND" for a in i.findall("action"))]
assert len(single) == 1
assert [d.get(android + "mimeType") for d in single[0].findall("data")] == ["text/plain"]
assert not any(p.get(android + "name") == "android.permission.POST_NOTIFICATIONS" for p in manifest.findall("uses-permission"))
main_plists = list((root / "ios").glob("*/Info.plist"))
extensions = []
for path in main_plists:
    with path.open("rb") as stream:
        info = plistlib.load(stream)
    if "NSExtension" in info:
        extensions.append(info)
    else:
        assert info["CFBundleDevelopmentRegion"] == "ru"
assert len(extensions) == (1 if args.ios_share_probe else 0), "Experimental iOS extension must be opt-in"
if extensions:
    assert extensions[0]["NSExtension"]["NSExtensionPointIdentifier"] == "com.apple.share-services"
print("Native config boundaries passed (not a device/runtime test)")
