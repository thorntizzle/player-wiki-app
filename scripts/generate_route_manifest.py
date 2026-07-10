from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from player_wiki.route_contracts import MANIFEST_PATH, RouteContractError, manifest_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the deterministic Flask route/access manifest.")
    parser.add_argument("--check", action="store_true", help="Fail when the committed manifest is stale.")
    args = parser.parse_args()

    try:
        expected = manifest_bytes()
    except (OSError, RouteContractError, ValueError) as exc:
        print(f"route manifest error: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if not MANIFEST_PATH.exists():
            print(f"route manifest is missing: {MANIFEST_PATH.relative_to(PROJECT_ROOT)}", file=sys.stderr)
            return 1
        if MANIFEST_PATH.read_bytes() != expected:
            print(
                "route manifest is stale; run python -B scripts/generate_route_manifest.py",
                file=sys.stderr,
            )
            return 1
        print(f"route manifest is current: {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
        return 0

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_bytes(expected)
    print(f"wrote {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
