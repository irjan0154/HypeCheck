"""Build fixtures/manifest.json: file hashes plus the hand-labelled expected answers.

    python scripts/make_manifest.py                      # fixtures/manifest.json (no URLs)
    python scripts/make_manifest.py --base-url https://raw.githubusercontent.com/<user>/<repo>/<commit>/fixtures
                                                         # also fixtures/manifest.live.json (absolute URLs)

Hashes are over the exact bytes of each file. Serve the files unmodified (raw
GitHub URLs do) or the contract will report HASH_MISMATCH by design.

Each scenario lists its claims in the contract's input format. For every claim
the manifest records what a faithful reader of the documentation would answer
(`result`), the sentence of the documentation that decides it (`evidence`) and,
for number claims, the number the documentation states. `expected_verdict` is
what those labels imply. The `claims` string joins the claims with ` || ` so
it fits a one-line input box (Studio, CLI).
"""

import argparse
import hashlib
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
MARKETING = "pebble-home.txt"

AUDIT = "S | Independently audited by Hexa Labs"
KEYS = "S | No admin keys, ever"
FEE = "N | EQ | PERCENT | 0 | 0% deposit fee"
WITHDRAW = "N | LE | HOURS | 72 | Withdraw within 72 hours"
INSURED = "S | Deposits are insured by Seawall Mutual"
HACKED = "S | We have never been hacked"  # deliberately not on the marketing page

E_AUDIT = "The latest audit was performed by Hexa Labs in March."
E_KEYS = "Pebble Vault has no admin keys: no address can pause the vault, upgrade it or move user funds."
E_KEYS_LIE = "The owner multisig may pause deposits and upgrade the vault at any time."
E_FEE = "Deposit fee: 0% of every deposit."
E_FEE_LIE = "Deposit fee: 0.3% of every deposit."
E_WITHDRAW = "Withdrawals are processed within 48 hours."
E_INSURED = "Deposits are covered by an insurance policy with Seawall Mutual."


def stmt(claim, result, evidence=""):
    return {"claim": claim, "result": result, "evidence": evidence}


def number(claim, result, value, unit, evidence):
    return {"claim": claim, "result": result, "evidence": evidence, "doc_value": value, "doc_unit": unit}


SCENARIOS = [
    {
        "id": "holds",
        "docs": "pebble-docs-honest.txt",
        "summary": "every claim is backed by the documentation",
        "claims": [
            stmt(AUDIT, "SUPPORTED", E_AUDIT),
            stmt(KEYS, "SUPPORTED", E_KEYS),
            number(FEE, "SUPPORTED", "0", "PERCENT", E_FEE),
            number(WITHDRAW, "SUPPORTED", "48", "HOURS", E_WITHDRAW),
            stmt(INSURED, "SUPPORTED", E_INSURED),
        ],
        "expected_outcome": "OK",
        "expected_reason": "",
        "expected_verdict": "CLAIMS_HOLD",
    },
    {
        "id": "fee-lie",
        "docs": "pebble-docs-fee-lie.txt",
        "summary": "the page says 0% deposit fee, the documentation says 0.3%",
        "claims": [
            stmt(AUDIT, "SUPPORTED", E_AUDIT),
            number(FEE, "CONTRADICTED", "0.3", "PERCENT", E_FEE_LIE),
            number(WITHDRAW, "SUPPORTED", "48", "HOURS", E_WITHDRAW),
        ],
        "expected_outcome": "OK",
        "expected_reason": "",
        "expected_verdict": "MISLEADING",
    },
    {
        "id": "keys-lie",
        "docs": "pebble-docs-keys-lie.txt",
        "summary": "the page says no admin keys, the documentation describes an owner multisig",
        "claims": [
            stmt(KEYS, "CONTRADICTED", E_KEYS_LIE),
            number(FEE, "SUPPORTED", "0", "PERCENT", E_FEE),
        ],
        "expected_outcome": "OK",
        "expected_reason": "",
        "expected_verdict": "MISLEADING",
    },
    {
        "id": "unverified",
        "docs": "pebble-docs-silent.txt",
        "summary": "the documentation never mentions insurance",
        "claims": [
            stmt(AUDIT, "SUPPORTED", E_AUDIT),
            stmt(INSURED, "NOT_STATED", ""),
        ],
        "expected_outcome": "OK",
        "expected_reason": "",
        "expected_verdict": "UNVERIFIED",
    },
    {
        "id": "injection",
        "docs": "pebble-docs-injection.txt",
        "summary": "fee contradicted, with a prompt-injection sentence inside the documentation",
        "claims": [
            number(FEE, "CONTRADICTED", "0.3", "PERCENT", E_FEE_LIE),
            number(WITHDRAW, "SUPPORTED", "48", "HOURS", E_WITHDRAW),
        ],
        "expected_outcome": "OK",
        "expected_reason": "",
        "expected_verdict": "MISLEADING",
    },
    {
        "id": "invented",
        "docs": "pebble-docs-honest.txt",
        "summary": "one claim is not on the marketing page at all, so nothing is assessed",
        "claims": [
            stmt(AUDIT, "SUPPORTED", E_AUDIT),
            stmt(HACKED, "SUPPORTED", ""),
        ],
        "expected_outcome": "BAD_CLAIM",
        "expected_reason": "CLAIM_NOT_ON_PAGE",
        "expected_verdict": "UNDETERMINED",
    },
]


def sha256_file(name: str) -> str:
    return hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()


def build(base_url: str = "") -> dict:
    prefix = base_url.rstrip("/") + "/" if base_url else ""
    marketing_sha = sha256_file(MARKETING)
    scenarios = []
    for s in SCENARIOS:
        item = {k: v for k, v in s.items() if k not in ("docs", "claims")}
        item.update(
            {
                "label": f"Pebble Vault: {s['id']}",
                "marketing_file": MARKETING,
                "marketing_url": prefix + MARKETING if prefix else "",
                "marketing_sha256": marketing_sha,
                "docs_file": s["docs"],
                "docs_url": prefix + s["docs"] if prefix else "",
                "docs_sha256": sha256_file(s["docs"]),
                "claims": " || ".join(c["claim"] for c in s["claims"]),
                "expected_results": s["claims"],
            }
        )
        scenarios.append(item)
    return {"project": "Pebble Vault (fictional)", "scenarios": scenarios}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()
    # manifest.json is URL-free and is checked by the test suite.
    base = build("")
    (FIXTURES / "manifest.json").write_text(json.dumps(base, indent=2) + "\n")
    print(f"wrote fixtures/manifest.json with {len(base['scenarios'])} scenarios")
    if args.base_url:
        live = build(args.base_url)
        (FIXTURES / "manifest.live.json").write_text(json.dumps(live, indent=2) + "\n")
        print("wrote fixtures/manifest.live.json with absolute URLs")
