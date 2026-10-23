"""File/request adapter for the native manifest engine."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", nargs="?", type=Path, help="JSON operation request")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--html", type=Path, help="write disconnected keyboard review")
    args = parser.parse_args(argv)
    if args.stdin == (args.request is not None):
        parser.error("provide one request file or --stdin")
    try:
        from ctm_variants.review import request, document
        payload = json.load(sys.stdin) if args.stdin else json.loads(args.request.read_text(encoding="utf-8"))
        result = request(payload)
        if args.html is not None:
            args.html.write_bytes(document(result).encode("utf-8"))
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 0
    except Exception as error:
        print("variant authoring failed: {}".format(error), file=sys.stderr)
        return 1
