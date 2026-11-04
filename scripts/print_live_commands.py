"""Print the exact GenLayer CLI commands for the live run, one block per scenario.

    python scripts/print_live_commands.py <contract-address>

Reads fixtures/manifest.live.json (see scripts/make_manifest.py). Nothing is
executed: copy each block into a terminal. Run the scenarios in order on a
fresh deployment so check ids are 1, 2, 3 ... in the order printed.
A proposer may have at most 5 checks in flight, so each block assesses its
check before the next one is proposed. The claims argument uses ` || ` between
claims so it stays a single line (Studio inputs are one line as well).
"""

import json
import shlex
import sys
from pathlib import Path

LIVE = Path(__file__).resolve().parent.parent / "fixtures" / "manifest.live.json"


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("0x"):
        print(__doc__)
        return 2
    address = sys.argv[1]
    if not LIVE.exists():
        print("fixtures/manifest.live.json is missing: run make_manifest.py with --base-url first")
        return 1
    scenarios = json.loads(LIVE.read_text())["scenarios"]
    for index, s in enumerate(scenarios, start=1):
        if not s["marketing_url"] or not s["docs_url"]:
            print(f"scenario {s['id']} has no URL in the live manifest")
            return 1
        propose = " ".join(
            shlex.quote(str(a))
            for a in (
                s["label"],
                s["marketing_url"],
                s["marketing_sha256"],
                s["docs_url"],
                s["docs_sha256"],
                s["claims"],
            )
        )
        print(f"# --- {index}. {s['id']}: {s['summary']}")
        print(f"# expected verdict: {s['expected_verdict']}")
        print(f"genlayer write {address} propose_check --args {propose}")
        print(f"genlayer write {address} assess --args {index}")
        print(f"genlayer call {address} get_check --args {index}")
        print(f"genlayer call {address} get_results --args {index}")
        print()
    print(f"genlayer call {address} get_stats")
    return 0


if __name__ == "__main__":
    sys.exit(main())
