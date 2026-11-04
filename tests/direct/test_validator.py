"""Consensus behaviour: what a validator accepts and what it rejects.

`run_validator()` replays the validator function captured from the last
`assess` call. Mocks apply at replay time, so swapping them simulates a
validator that sees different pages or a different model answer.
"""

import copy

import pytest

from conftest import (
    ALL_CLAIMS,
    C_AUDIT,
    C_FEE,
    C_INSURED,
    C_WITHDRAW,
    DOC_URL,
    DOCS,
    HONEST,
    MARKETING,
    MKT_URL,
    Q_AUDIT,
    Q_FEE,
    Q_PAUSE,
    Q_WITHDRAW,
    num,
    stmt,
)


@pytest.fixture
def assessed(env):
    """A finished, honest round: leaves one captured validator behind."""
    env.run()
    assert len(env.vm._captured_validators) == 1
    return env


def forged(env, mutate):
    result = copy.deepcopy(env.captured())
    mutate(result)
    return result


def test_exactly_one_nondeterministic_round_per_assess(assessed):
    assessed.vm.clear_validators()
    cid = assessed.propose()
    assessed.c.assess(cid)
    assert len(assessed.vm._captured_validators) == 1


# ------------------------------------------------ honest leader, honest view


def test_validator_agrees_with_an_honest_leader(assessed):
    assert assessed.vm.run_validator() is True


def test_validator_may_differ_on_quotes(assessed):
    assessed.reset()
    assessed.serve()
    assessed.model(
        [
            stmt(0, "SUPPORTED", "performed by Hexa Labs"),
            stmt(1, "CONTRADICTED", "may pause deposits at any time"),
            num(2, "0.3", "PERCENT", "Deposit fee: 0.3%"),
            num(3, "48", "HOURS", "within 48 hours"),
        ]
    )
    assert assessed.vm.run_validator() is True


def test_validator_may_write_the_number_in_other_units(env):
    # the documentation states the same fee twice, as a percentage and in basis points
    docs = DOCS + "\nThe fee is 30 bps.\n"
    env.run([num(0, "0.3", "PERCENT", Q_FEE)], C_FEE, MARKETING, docs)
    assert env.results(1)[0]["result"] == "CONTRADICTED"
    env.reset()
    env.serve(MARKETING, docs)
    env.model([num(0, "30", "BPS", "The fee is 30 bps.")])
    assert env.vm.run_validator() is True  # 0.3 PERCENT and 30 BPS are the same number


# ------------------------------------------- validator sees something else


def test_validator_disagrees_when_its_model_judges_differently(assessed):
    assessed.reset()
    assessed.serve()
    entries = copy.deepcopy(HONEST)
    entries[0] = stmt(0, "CONTRADICTED", Q_AUDIT)
    assessed.model(entries)
    assert assessed.vm.run_validator() is False


def test_validator_disagrees_when_its_model_is_unsure(assessed):
    assessed.reset()
    assessed.serve()
    entries = copy.deepcopy(HONEST)
    entries[1] = stmt(1, "UNCLEAR", Q_PAUSE)
    assessed.model(entries)
    assert assessed.vm.run_validator() is False


def test_validator_disagrees_when_it_reads_a_different_number(assessed):
    assessed.reset()
    assessed.serve()
    entries = copy.deepcopy(HONEST)
    entries[2] = num(2, "0", "PERCENT", Q_FEE)  # a piece of 0.3: unclear for this validator
    assessed.model(entries)
    assert assessed.vm.run_validator() is False


def test_validator_disagrees_when_the_documentation_does_not_match_the_commitment(assessed):
    assessed.reset()
    assessed.serve(MARKETING, DOCS + "\nA paragraph the proposer never committed to.\n")
    assessed.model()
    assert assessed.vm.run_validator() is False


def test_validator_disagrees_when_the_marketing_page_does_not_match_the_commitment(assessed):
    assessed.reset()
    assessed.serve(MARKETING + "\nNew slogan.\n", DOCS)
    assessed.model()
    assert assessed.vm.run_validator() is False


def test_validator_disagrees_when_its_model_answers_garbage(assessed):
    assessed.reset()
    assessed.serve()
    assessed.model_raw("I am sorry, I cannot do that.")
    assert assessed.vm.run_validator() is False


def test_validator_disagrees_when_its_source_is_down(assessed):
    assessed.reset()
    assessed.serve_status(MKT_URL, 503)
    assessed.serve_status(DOC_URL, 503)
    assessed.model()
    assert assessed.vm.run_validator() is False


# ------------------------------------------------------------ forged leader


def test_validator_rejects_a_leader_that_hides_the_results(assessed):
    def hide(r):
        r["results"] = []

    assert assessed.vm.run_validator(leader_result=forged(assessed, hide)) is False


def test_validator_rejects_a_leader_that_flips_a_result(assessed):
    def flip(r):
        r["results"][1]["result"] = "SUPPORTED"

    assert assessed.vm.run_validator(leader_result=forged(assessed, flip)) is False


def test_validator_rejects_a_leader_that_invents_a_result(assessed):
    def invent(r):
        r["results"].append(
            {"id": 4, "kind": "STATEMENT", "result": "CONTRADICTED", "doc_value": "", "doc_unit": "", "quote": Q_PAUSE}
        )

    assert assessed.vm.run_validator(leader_result=forged(assessed, invent)) is False


def test_validator_rejects_a_leader_that_claims_a_different_outcome(assessed):
    def claim(r):
        r["outcome"], r["reason"], r["results"] = "TOO_LARGE", "DOC_SIZE_DOCS", []

    assert assessed.vm.run_validator(leader_result=forged(assessed, claim)) is False


def test_validator_rejects_a_leader_that_changes_only_the_outcome(assessed):
    def claim(r):
        r["outcome"] = "TOO_LARGE"  # reason and results left as they were

    assert assessed.vm.run_validator(leader_result=forged(assessed, claim)) is False


@pytest.mark.parametrize(
    "index, field, value",
    [
        (0, "quote", "They audited everything twice."),  # not in the documentation
        (0, "quote", "x" * 400),
        (1, "quote", ""),  # a decisive answer without evidence
        (0, "kind", "NUMBER"),
        (0, "id", 5),
        (0, "id", True),
        (0, "doc_value", "7"),  # a statement carries no number
        (0, "doc_unit", "DAYS"),
        (2, "doc_value", "0"),  # the number is not in the quote and flips the comparison
        (2, "doc_value", ""),
        (2, "doc_unit", "BPS"),  # same words, a different unit: same result, forged number
        (2, "doc_unit", "PARSECS"),
        (2, "doc_value", "0.30"),  # not the number written in the quote
        (0, "result", "MAYBE"),
    ],
)
def test_validator_rejects_a_leader_that_stores_forged_fields(assessed, index, field, value):
    def forge(r):
        r["results"][index][field] = value

    assert assessed.vm.run_validator(leader_result=forged(assessed, forge)) is False


def test_validator_rejects_a_leader_that_stores_an_extra_or_missing_field(assessed):
    def extra(r):
        r["results"][0]["note"] = "smuggled"

    def missing(r):
        del r["results"][0]["quote"]

    assert assessed.vm.run_validator(leader_result=forged(assessed, extra)) is False
    assert assessed.vm.run_validator(leader_result=forged(assessed, missing)) is False


@pytest.mark.parametrize(
    "bad",
    [None, "MISLEADING", 7, [], {}, {"outcome": "OK"}, {"outcome": "OK", "reason": "", "results": "x"}],
)
def test_validator_rejects_malformed_leader_results(assessed, bad):
    assert assessed.vm.run_validator(leader_result=bad) is False


# ------------------------------- results that carry no evidence (isolated rules)


def test_not_stated_must_carry_no_quote(env):
    env.run([stmt(0, "NOT_STATED")], C_INSURED)
    assert env.vm.run_validator() is True

    def forge(r):
        r["results"][0]["quote"] = Q_AUDIT  # a real excerpt, but NOT_STATED has no evidence

    assert env.vm.run_validator(leader_result=forged(env, forge)) is False


def test_unclear_may_only_keep_a_real_excerpt(env):
    env.run([stmt(0, "UNCLEAR", Q_PAUSE)], "S | No admin keys, ever")
    assert env.vm.run_validator() is True

    def forge(r):
        r["results"][0]["quote"] = "made up"

    assert env.vm.run_validator(leader_result=forged(env, forge)) is False


def test_a_number_result_needs_the_number_to_be_in_its_quote(env):
    env.run([num(0, "48", "HOURS", Q_WITHDRAW)], C_WITHDRAW)
    assert env.vm.run_validator() is True

    def forge(r):
        r["results"][0]["quote"] = Q_AUDIT  # a real excerpt that does not contain 48

    assert env.vm.run_validator(leader_result=forged(env, forge)) is False


# ---------------------------------------- recorded outcomes without a model


def test_claim_not_on_page_is_agreed_and_cannot_be_forged_away(env):
    env.serve()
    cid = env.propose("S | We have never been hacked")
    env.c.assess(cid)
    assert env.info(cid)["reason"] == "CLAIM_NOT_ON_PAGE"
    assert env.vm.run_validator() is True  # no model is consulted on either side

    def forge(r):
        r["outcome"], r["reason"] = "OK", ""  # pretend the claim was judged

    assert env.vm.run_validator(leader_result=forged(env, forge)) is False

    def forge_reason(r):
        r["reason"] = "DOC_SIZE_DOCS"

    assert env.vm.run_validator(leader_result=forged(env, forge_reason)) is False


def test_validators_agree_on_a_hash_mismatch_only_if_they_see_it_too(env):
    env.serve(MARKETING, DOCS + "\nDrift.\n")
    cid = env.propose(C_AUDIT)
    env.c.assess(cid)
    assert env.info(cid)["status"] == "RETRYABLE"
    assert env.vm.run_validator() is True  # same bytes, same mismatch
    env.reset()
    env.serve()
    env.model([stmt(0, "SUPPORTED", Q_AUDIT)])
    assert env.vm.run_validator() is False  # this validator saw the committed bytes


def test_mismatch_of_the_other_page_is_a_different_reason(env):
    env.serve(MARKETING, DOCS + "\nDrift.\n")
    cid = env.propose(C_AUDIT)
    env.c.assess(cid)
    env.reset()
    env.serve(MARKETING + "\nDrift.\n", DOCS)
    assert env.vm.run_validator() is False  # it sees HASH_MISMATCH_MARKETING, not _DOCS


# ----------------------------------------------------- leader raised an error


def test_leader_llm_error_never_gets_agreement(assessed):
    # the validator's own model works, so the leader is the odd one out
    assert assessed.vm.run_validator(leader_error=Exception("[LLM_ERROR] model call failed")) is False


def test_leader_llm_error_never_gets_agreement_even_if_the_validator_fails_too(assessed):
    assessed.reset()
    assessed.serve()
    assessed.model_raw("garbage")
    assert assessed.vm.run_validator(leader_error=Exception("[LLM_ERROR] model call failed")) is False


def test_external_errors_must_match_exactly(assessed):
    assessed.reset()
    assessed.serve_status(MKT_URL, 404)
    assessed.serve_status(DOC_URL, 404)
    assert assessed.vm.run_validator(leader_error=Exception("[EXTERNAL] HTTP 404")) is True
    assert assessed.vm.run_validator(leader_error=Exception("[EXTERNAL] HTTP 403")) is False


def test_external_leader_error_is_rejected_when_the_validator_reads_the_pages(assessed):
    assert assessed.vm.run_validator(leader_error=Exception("[EXTERNAL] HTTP 404")) is False


def test_transient_errors_agree_when_both_sides_are_transient(assessed):
    assessed.reset()
    assessed.serve_status(MKT_URL, 502)
    assessed.serve_status(DOC_URL, 502)
    assert assessed.vm.run_validator(leader_error=Exception("[TRANSIENT] fetch failed")) is True


def test_transient_leader_error_is_rejected_when_the_validator_succeeds(assessed):
    assert assessed.vm.run_validator(leader_error=Exception("[TRANSIENT] fetch failed")) is False


def test_transient_leader_vs_external_validator_do_not_agree(assessed):
    assessed.reset()
    assessed.serve_status(MKT_URL, 404)
    assessed.serve_status(DOC_URL, 404)
    assert assessed.vm.run_validator(leader_error=Exception("[TRANSIENT] fetch failed")) is False


def test_external_leader_vs_transient_validator_do_not_agree(assessed):
    assessed.reset()
    assessed.serve_status(MKT_URL, 502)
    assessed.serve_status(DOC_URL, 502)
    assert assessed.vm.run_validator(leader_error=Exception("[EXTERNAL] HTTP 404")) is False
    assert assessed.vm.run_validator(leader_error=Exception("[EXPECTED] BAD_CLAIM")) is False
    assert assessed.vm.run_validator(leader_error=Exception("[LLM_ERROR] model call failed")) is False


def test_unclassified_leader_errors_are_never_agreed(assessed):
    assert assessed.vm.run_validator(leader_error=Exception("boom")) is False
    assessed.reset()
    assessed.serve_status(MKT_URL, 404)
    assessed.serve_status(DOC_URL, 404)
    assert assessed.vm.run_validator(leader_error=Exception("boom")) is False
