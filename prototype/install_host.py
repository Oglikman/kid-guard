"""Registers (or removes) the KidGuard native-messaging host for Chrome and Edge under the current Windows user only (HKCU)."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

from kidguard import config

HERE = Path(__file__).resolve().parent
EXT_MANIFEST = HERE.parent / "extension" / "manifest.json"
HOST_DIR = HERE / "native_host_files"
REG_PATHS = {
    "Chrome": rf"Software\Google\Chrome\NativeMessagingHosts\{config.HOST_NAME}",
    "Edge": rf"Software\Microsoft\Edge\NativeMessagingHosts\{config.HOST_NAME}",
}


def extension_id_from_key(key_b64: str) -> str:
    """Computes Chrome's extension ID from the manifest's public key (first 16 bytes of SHA-256, hex mapped 0-f to a-p)."""
    digest = hashlib.sha256(base64.b64decode(key_b64)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in digest)


def build_host_manifest(bat_path: Path, ext_id: str) -> dict:
    """Returns the native-messaging host manifest, allowing only this extension to connect."""
    return {"name": config.HOST_NAME, "description": "KidGuard companion", "path": str(bat_path), "type": "stdio",
            "allowed_origins": [f"chrome-extension://{ext_id}/"]}


def write_files(ext_id: str) -> Path:
    """Writes the launcher .bat (absolute Python path) and the host manifest JSON, returning the manifest path."""
    HOST_DIR.mkdir(exist_ok=True)
    bat = HOST_DIR / "kidguard_host.bat"
    bat.write_text(f'@echo off\r\n"{sys.executable}" "{HERE / "native_host.py"}"\r\n')
    manifest = HOST_DIR / f"{config.HOST_NAME}.json"
    manifest.write_text(json.dumps(build_host_manifest(bat, ext_id), indent=2))
    return manifest


def main() -> int:
    """Installs or uninstalls the registry entries for Chrome and Edge; --dry-run prints the plan without changing anything."""
    ap = argparse.ArgumentParser(description="Install/uninstall the KidGuard native host")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--extension-id", help="override the ID computed from extension/manifest.json")
    args = ap.parse_args()

    ext_id = args.extension_id or extension_id_from_key(json.loads(EXT_MANIFEST.read_text())["key"])
    manifest = HOST_DIR / f"{config.HOST_NAME}.json"
    print(f"Extension ID: {ext_id}")
    for browser, path in REG_PATHS.items():
        print(f"  {'REMOVE' if args.uninstall else 'SET'} HKCU\\{path}" + ("" if args.uninstall else f" = {manifest}"))
    if args.dry_run:
        print("Dry run: nothing changed.")
        return 0

    import winreg
    if args.uninstall:
        for path in REG_PATHS.values():
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except FileNotFoundError:
                pass
        print("Registry entries removed. (Files in native_host_files/ left in place.)")
        return 0
    manifest = write_files(ext_id)
    for path in REG_PATHS.values():
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(manifest))
    print("Installed for Chrome and Edge (current Windows user). Restart the browser, then load the extension.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
