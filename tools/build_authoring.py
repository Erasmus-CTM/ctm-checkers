#!/usr/bin/env python3
"""Produce a native-only authoring directory; never alter browser payloads."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def produce(destination, *, check=False, root=ROOT):
    source = root / "authoring" / "ctm_variants"
    entries = {"ctm_variants/" + path.name: path.read_bytes()
               for path in sorted(source.glob("*.py"))}
    entries["ctm-variants.py"] = (root / "authoring" / "ctm-variants.py").read_bytes()
    entries["ctm-variants-bot.py"] = (root / "authoring" / "ctm-variants-bot.py").read_bytes()
    entries["LICENSE"] = (root / "LICENSE").read_bytes()
    report = {"version": 1, "kind": "native-authoring", "files": {
        name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(entries.items())}}
    entries["native.json"] = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    destination = Path(destination)
    actual = {path.relative_to(destination).as_posix(): path.read_bytes()
              for path in destination.rglob("*") if path.is_file() and not
              (path.suffix == ".pyc" and path.parent.name == "__pycache__")} if destination.exists() else {}
    if check:
        if actual != entries:
            raise ValueError("native authoring distribution differs from canonical source")
    else:
        # Destination is explicit caller-owned generated output. Refuse stale
        # extra files rather than recursively deleting a possibly wrong path.
        if set(actual) - set(entries):
            raise ValueError("native output contains unexpected files; use a fresh destination")
        for name, data in entries.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return report


def install(extension, *, check=False, root=ROOT):
    """Install the native seam beside an already materialized checker payload.

    This is a separate producer from the committed six-file browser extension.
    The umbrella invokes it against its installed extension at an exact source
    ref; no browser wheel, script or checker manifest is regenerated here.
    """
    extension = Path(extension)
    if not (extension / "checkers.json").is_file() or not (extension / "_extension.yml").is_file():
        raise ValueError("native install requires an installed ctm-checkers extension")
    return produce(extension / "native-authoring", check=check, root=root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path)
    destination.add_argument("--install-extension", type=Path,
                             help="install native-authoring beside a materialized ctm-checkers payload")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.install_extension is not None:
        install(args.install_extension, check=args.check)
    else:
        produce(args.output, check=args.check)


if __name__ == "__main__":
    main()
