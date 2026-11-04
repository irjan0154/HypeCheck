"""The synthetic fixtures behave as labelled, and the manifest matches the files."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
import make_manifest  # noqa: E402

MANIFEST = json.loads((FIX / "manifest.json").read_text())
SCENARIOS = MANIFEST["scenarios"]
IDS = [s["id"] for s in SCENARIOS]


def read(name):
    return (FIX / name).read_text()


def faithful_entries(scenario):
    """What a model that reads the documentation correctly would answer, from the hand labels."""
    entries = []
    for i, c in enumerate(scenario["expected_results"]):
        if c["claim"].startswith("N |"):
            entries.append(
                {"id": i, "found": True, "value": c["doc_value"], "unit": c["doc_unit"], "quote": c["evidence"]}
            )
        else:
            entries.append({"id": i, "answer": c["result"], "quote": c["evidence"]})
    return entries


def test_manifest_is_current():
    assert MANIFEST == make_manifest.build("")


def test_manifest_has_no_urls_and_the_live_one_is_not_committed():
    assert all(s["marketing_url"] == "" and s["docs_url"] == "" for s in SCENARIOS)
    assert not (FIX / "manifest.live.json").exists() or "raw.githubusercontent.com" in (
        FIX / "manifest.live.json"
    ).read_text()


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_manifest_hashes_match_the_exact_bytes(scenario):
    for side in ("marketing", "docs"):
        data = (FIX / scenario[f"{side}_file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == scenario[f"{side}_sha256"]


@pytest.mark.parametrize("name", sorted(p.name for p in FIX.glob("*.txt")))
def test_fixture_files_are_plain_lf_utf8(name):
    data = (FIX / name).read_bytes()
    assert b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")
    data.decode("utf-8")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_every_scenario_is_within_the_contract_bounds(fns, scenario):
    for side in ("marketing", "docs"):
        assert len((FIX / scenario[f"{side}_file"]).read_bytes()) < fns.MAX_DOC_BYTES
    claims, err = fns.parse_claims(scenario["claims"])
    assert err == ""
    assert len(claims) <= fns.MAX_CLAIMS
    assert len(claims) == len(scenario["expected_results"])
    assert all(len(c["text"]) <= fns.MAX_CLAIM_CHARS for c in claims)
    assert len(scenario["label"]) <= fns.MAX_LABEL_CHARS
    assert "\n" not in scenario["claims"]  # one line, so it fits a one-line input box


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_claims_are_on_the_marketing_page_exactly_when_labelled(fns, scenario):
    claims, _ = fns.parse_claims(scenario["claims"])
    on_page = fns.claims_in_marketing(claims, read(scenario["marketing_file"]))
    assert on_page == (scenario["expected_reason"] != "CLAIM_NOT_ON_PAGE")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_labels_imply_the_expected_verdict(fns, scenario):
    results = [{"result": c["result"]} for c in scenario["expected_results"]]
    assert fns.verdict_from(scenario["expected_outcome"], results) == scenario["expected_verdict"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_the_labelled_evidence_is_really_in_the_documentation(fns, scenario):
    docs = read(scenario["docs_file"])
    for c in scenario["expected_results"]:
        if c["evidence"]:
            assert fns.quote_grounded(c["evidence"], docs), c["claim"]
        elif scenario["expected_outcome"] == "OK":
            assert c["result"] == "NOT_STATED"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_contract_reaches_the_labelled_verdict_with_a_faithful_model(env, scenario):
    """End to end in direct mode: pages and model are mocked, the rest is the contract."""
    marketing = read(scenario["marketing_file"])
    docs = read(scenario["docs_file"])
    env.serve(marketing, docs)
    if scenario["expected_outcome"] == "OK":  # a BAD_CLAIM check must not consult the model
        env.model(faithful_entries(scenario))
    cid = env.propose(scenario["claims"], marketing, docs, label=scenario["label"])
    env.c.assess(cid)
    info = env.info(cid)
    assert info["status"] == "ASSESSED"
    assert info["verdict"] == scenario["expected_verdict"]
    assert info["reason"] == scenario["expected_reason"]
    if scenario["expected_outcome"] == "OK":
        got = [(r["id"], r["result"]) for r in env.results(cid)]
        assert got == [(i, c["result"]) for i, c in enumerate(scenario["expected_results"])]


def test_the_injection_fixture_really_contains_an_injection():
    text = read("pebble-docs-injection.txt")
    assert "ignore all previous instructions" in text.lower()
    for name in ("pebble-home.txt", "pebble-docs-honest.txt", "pebble-docs-fee-lie.txt"):
        assert "ignore" not in read(name).lower()


def test_each_lie_differs_from_the_honest_docs_in_exactly_the_labelled_place():
    honest = read("pebble-docs-honest.txt").split("\n\n")
    for name, changed in (
        ("pebble-docs-fee-lie.txt", 1),
        ("pebble-docs-keys-lie.txt", 1),
        ("pebble-docs-injection.txt", 1),
        ("pebble-docs-silent.txt", 1),
    ):
        other = read(name).split("\n\n")
        differing = [p for p in other if p not in honest]
        if name.endswith("silent.txt"):
            assert differing == [] and len(other) == len(honest) - 1
        else:
            assert len(differing) == changed


def test_fixtures_describe_only_a_fictional_project():
    for path in FIX.glob("*.txt"):
        text = path.read_text()
        assert "fictional protocol" in text
        assert "@pebblevault.example" in text  # reserved .example domain, never a real mailbox
