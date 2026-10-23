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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    produce(args.output, check=args.check)


if __name__ == "__main__":
    main()
