"""Read private staging MIME mail on the Docker host, only via operator SSH.

Do not copy the output (one-time login/reset links) into tickets or chat logs.
"""
import argparse
from email import policy
from email.parser import BytesParser
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message", nargs="?", help="32-hex .eml filename; omit to list metadata")
    parser.add_argument("--volume", default="teleiosis-staging_capture_mail")
    args = parser.parse_args()
    root = Path(subprocess.check_output([
        "docker", "volume", "inspect", args.volume, "--format", "{{.Mountpoint}}"
    ], text=True).strip())
    if args.message:
        if not re.fullmatch(r"[a-f0-9]{32}\.eml", args.message):
            parser.error("Pass a filename from the list, without directories")
        message = BytesParser(policy=policy.default).parsebytes((root / args.message).read_bytes())
        print("To:", message["To"])
        print("Subject:", message["Subject"])
        print(message.get_content())
    else:
        for file in sorted(root.glob("*.eml"), key=lambda p: p.stat().st_mtime):
            message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
            print(file.name, message["To"], message["Subject"])


if __name__ == "__main__":
    main()
