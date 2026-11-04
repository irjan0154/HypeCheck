"""Deterministic helpers: claims, numbers, evidence grounding, verdict."""

import pytest

DOCS = (
    "Pebble Vault documentation.\n\n"
    "Deposit fee: 0.3% of every deposit.\n\n"
    "The owner multisig may pause deposits at any time.\n\n"
    "Withdrawals are processed within 48 hours."
)


def number_claim(fns, line):
    claims, err = fns.parse_claims(line)
    assert err == "", err
    return claims[0]


# ------------------------------------------------------------------ urls


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://docs.example.com/page.txt", True),
        ("https://docs.example.com:443/page", True),
        ("http://docs.example.com/page", False),
        ("https://user:pw@docs.example.com/", False),
        ("https://user@docs.example.com/", False),
        ("https://10.0.0.1/page", False),
        ("https://localhost/page", False),
        ("https://intranet.internal/page", False),
        ("https://docs.example.com:8443/page", False),
        ("https://docs/page", False),
        ("https://docs.example.com/a b", False),
        ("", False),
        ("https://" + "a" * 300 + ".com", False),
    ],
)
def test_url_admissible(fns, url, ok):
    assert fns.url_admissible(url) is ok


def test_hash_helpers(fns):
    h = fns.sha256_hex(b"abc")
    assert fns.is_sha256_hex(h)
    assert not fns.is_sha256_hex(h.upper())
    assert not fns.is_sha256_hex(h[:-1])


# ---------------------------------------------------------------- numbers


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0", 0),
        ("1", 1_000_000),
        ("0.3", 300_000),
        ("12.345678", 12_345_678),
        ("0.0000001", None),  # more than 6 decimals
        ("", None),
        (".5", None),
        ("5.", None),
        ("-1", None),
        ("1e3", None),
        ("1,000", None),
        ("١٢", None),  # non-ASCII digits
        ("1" * 30, None),
        (3, None),
    ],
)
def test_parse_decimal(fns, text, expected):
    assert fns.parse_decimal(text) == expected


def test_normalize_units_agree(fns):
    assert fns.normalize_number("0.3", "PERCENT") == fns.normalize_number("30", "BPS")
    assert fns.normalize_number("2", "DAYS") == fns.normalize_number("48", "HOURS")
    assert fns.normalize_number("90", "MINUTES") == fns.normalize_number("1.5", "HOURS")
    assert fns.normalize_number("5", "COUNT")[0] == "COUNT"


def test_normalize_rejects_unknown_unit_or_value(fns):
    assert fns.normalize_number("1", "PARSECS") is None
    assert fns.normalize_number("x", "PERCENT") is None
    assert fns.normalize_number("1", None) is None


def test_units_of_different_groups_never_compare(fns):
    claim = number_claim(fns, "N | EQ | PERCENT | 0 | 0% deposit fee")
    assert fns.number_result(claim, "0", "DAYS") == "UNCLEAR"


@pytest.mark.parametrize(
    "op,claimed,unit,doc_value,doc_unit,expected",
    [
        ("EQ", "0", "PERCENT", "0", "PERCENT", "SUPPORTED"),
        ("EQ", "0", "PERCENT", "0.3", "PERCENT", "CONTRADICTED"),
        ("EQ", "0.3", "PERCENT", "30", "BPS", "SUPPORTED"),
        ("LE", "1", "PERCENT", "0.3", "PERCENT", "SUPPORTED"),
        ("LE", "1", "PERCENT", "1", "PERCENT", "SUPPORTED"),
        ("LE", "1", "PERCENT", "1.5", "PERCENT", "CONTRADICTED"),
        ("GE", "99", "PERCENT", "95", "PERCENT", "CONTRADICTED"),
        ("GE", "99", "PERCENT", "99", "PERCENT", "SUPPORTED"),
        ("LE", "72", "HOURS", "2", "DAYS", "SUPPORTED"),
        ("LE", "24", "HOURS", "48", "HOURS", "CONTRADICTED"),
        ("EQ", "7", "DAYS", "168", "HOURS", "SUPPORTED"),
    ],
)
def test_number_result_table(fns, op, claimed, unit, doc_value, doc_unit, expected):
    claim = number_claim(fns, f"N | {op} | {unit} | {claimed} | claim says {claimed}")
    assert fns.number_result(claim, doc_value, doc_unit) == expected


def test_number_result_unparsable_is_unclear(fns):
    claim = number_claim(fns, "N | EQ | PERCENT | 0 | 0% deposit fee")
    assert fns.number_result(claim, "zero", "PERCENT") == "UNCLEAR"
    assert fns.number_result(claim, "0", "PARSECS") == "UNCLEAR"


def test_number_result_with_an_unknown_operator_is_unclear(fns):
    claim = number_claim(fns, "N | EQ | PERCENT | 0 | 0% deposit fee")
    claim["op"] = "NE"  # parse_claims never produces it; the comparison still fails closed
    assert fns.number_result(claim, "0", "PERCENT") == "UNCLEAR"
    assert fns.number_result(claim, "5", "PERCENT") == "UNCLEAR"


# ----------------------------------------------------------------- claims


def test_parse_statement_and_number(fns):
    claims, err = fns.parse_claims(
        "S | The vault has no admin keys\n"
        "\n"
        "N | EQ | PERCENT | 0 | 0% deposit fee\n"
    )
    assert err == ""
    assert [c["id"] for c in claims] == [0, 1]
    assert claims[0] == {
        "id": 0, "kind": "STATEMENT", "text": "The vault has no admin keys",
        "op": "", "unit": "", "value": "",
    }
    assert claims[1]["kind"] == "NUMBER"
    assert (claims[1]["op"], claims[1]["unit"], claims[1]["value"]) == ("EQ", "PERCENT", "0")


def test_claim_text_may_contain_bars_and_whitespace_is_collapsed(fns):
    claims, err = fns.parse_claims("S |   fast   |  cheap \n")
    assert err == ""
    assert claims[0]["text"] == "fast | cheap"


def test_claims_can_be_separated_by_double_bars_on_one_line(fns):
    claims, err = fns.parse_claims("S | No admin keys || N | EQ | PERCENT | 0 | 0% deposit fee ||S | Audited")
    assert err == ""
    assert [c["kind"] for c in claims] == ["STATEMENT", "NUMBER", "STATEMENT"]
    assert [c["text"] for c in claims] == ["No admin keys", "0% deposit fee", "Audited"]
    assert [c["id"] for c in claims] == [0, 1, 2]


@pytest.mark.parametrize(
    "raw,code",
    [
        ("", "NO_CLAIMS"),
        ("||", "NO_CLAIMS"),
        ("S | a || b", "BAD_CLAIM"),  # a claim text may not contain a double bar
        ("\n  \n", "NO_CLAIMS"),
        (5, "BAD_CLAIM"),
        ("just text", "BAD_CLAIM"),
        ("X | text", "BAD_CLAIM"),
        ("S |   ", "BAD_CLAIM"),
        ("N | EQ | PERCENT | 0", "BAD_CLAIM"),
        ("N | NE | PERCENT | 0 | 0% fee", "BAD_CLAIM"),
        ("N | EQ | PARSECS | 0 | 0 parsecs", "BAD_CLAIM"),
        ("N | EQ | PERCENT | zero | zero percent fee", "BAD_NUMBER"),
        ("N | EQ | PERCENT | 0.5 | 0% fee", "BAD_NUMBER"),  # value not in the claim text
        ("S | a\nS | A", "DUPLICATE_CLAIM"),
        ("S | " + "x" * 201, "CLAIM_TOO_LONG"),
    ],
)
def test_parse_claims_rejections(fns, raw, code):
    claims, err = fns.parse_claims(raw)
    assert claims is None
    assert err == code


def test_claim_count_bound(fns):
    ok = "\n".join(f"S | claim {i}" for i in range(fns.MAX_CLAIMS))
    assert fns.parse_claims(ok)[1] == ""
    too_many = ok + "\nS | one more"
    assert fns.parse_claims(too_many) == (None, "TOO_MANY_CLAIMS")


def test_claims_must_appear_in_marketing(fns):
    claims, _ = fns.parse_claims("S | No admin keys\nN | EQ | PERCENT | 0 | 0% deposit fee")
    page = "Pebble Vault\n\nNo   admin keys.  Ever.\n\n0% deposit fee, always."
    assert fns.claims_in_marketing(claims, page)
    assert fns.claims_in_marketing(claims, page.upper())
    assert not fns.claims_in_marketing(claims, "No admin keys here. Fee is 0.3%.")


# --------------------------------------------------------------- evidence


def test_quote_grounded(fns):
    assert fns.quote_grounded("Deposit fee: 0.3% of every deposit.", DOCS)
    assert fns.quote_grounded("deposit   FEE: 0.3%", DOCS)
    assert not fns.quote_grounded("", DOCS)
    assert not fns.quote_grounded("There is no deposit fee.", DOCS)
    assert not fns.quote_grounded("a" * 201, DOCS + "a" * 300)


def statement_entry(claim, answer, quote):
    return {"id": claim["id"], "answer": answer, "quote": quote}


def test_statement_supported_with_grounded_quote(fns):
    claim = fns.parse_claims("S | Withdrawals take two days")[0][0]
    r = fns.evaluate_claim(
        claim, statement_entry(claim, "SUPPORTED", "Withdrawals are processed within 48 hours."), DOCS
    )
    assert r["result"] == "SUPPORTED"
    assert r["quote"] == "Withdrawals are processed within 48 hours."


@pytest.mark.parametrize("answer", ["SUPPORTED", "CONTRADICTED"])
def test_decisive_statement_without_grounded_quote_is_unclear(fns, answer):
    claim = fns.parse_claims("S | No admin keys")[0][0]
    for quote in ("", "The owner has no keys at all."):
        r = fns.evaluate_claim(claim, statement_entry(claim, answer, quote), DOCS)
        assert r["result"] == "UNCLEAR"
        assert r["quote"] == ""


def test_statement_contradicted_with_grounded_quote(fns):
    claim = fns.parse_claims("S | No admin keys")[0][0]
    r = fns.evaluate_claim(
        claim,
        statement_entry(claim, "CONTRADICTED", "The owner multisig may pause deposits at any time."),
        DOCS,
    )
    assert r["result"] == "CONTRADICTED"
    assert r["quote"].startswith("The owner multisig")


def test_not_stated_keeps_no_quote(fns):
    claim = fns.parse_claims("S | Insured up to one million")[0][0]
    r = fns.evaluate_claim(claim, statement_entry(claim, "NOT_STATED", "Deposit fee: 0.3%"), DOCS)
    assert r["result"] == "NOT_STATED"
    assert r["quote"] == ""


def test_unclear_statement_keeps_only_a_grounded_quote(fns):
    claim = fns.parse_claims("S | Fast withdrawals")[0][0]
    grounded = fns.evaluate_claim(
        claim, statement_entry(claim, "UNCLEAR", "Withdrawals are processed within 48 hours."), DOCS
    )
    assert grounded["result"] == "UNCLEAR" and grounded["quote"] != ""
    ungrounded = fns.evaluate_claim(claim, statement_entry(claim, "UNCLEAR", "made up"), DOCS)
    assert ungrounded["result"] == "UNCLEAR" and ungrounded["quote"] == ""


@pytest.mark.parametrize(
    "entry",
    [
        None,
        "SUPPORTED",
        {"id": 0, "answer": "SUPPORTED"},
        {"id": 0, "answer": "SUPPORTED", "quote": "x", "extra": 1},
        {"id": 1, "answer": "SUPPORTED", "quote": ""},
        {"id": True, "answer": "SUPPORTED", "quote": ""},
        {"id": 0, "answer": "MAYBE", "quote": ""},
        {"id": 0, "answer": "SUPPORTED", "quote": 5},
    ],
)
def test_malformed_statement_entry_is_none(fns, entry):
    claim = fns.parse_claims("S | anything")[0][0]
    assert fns.evaluate_claim(claim, entry, DOCS) is None


def number_entry(claim, found=True, value="0.3", unit="PERCENT", quote="Deposit fee: 0.3% of every deposit."):
    return {"id": claim["id"], "found": found, "value": value, "unit": unit, "quote": quote}


def test_number_claim_contradicted_by_code(fns):
    claim = number_claim(fns, "N | EQ | PERCENT | 0 | 0% deposit fee")
    r = fns.evaluate_claim(claim, number_entry(claim), DOCS)
    assert r["result"] == "CONTRADICTED"
    assert (r["doc_value"], r["doc_unit"]) == ("0.3", "PERCENT")


def test_number_claim_supported_across_units(fns):
    claim = number_claim(fns, "N | LE | HOURS | 72 | withdrawals within 72 hours")
    entry = number_entry(
        claim, value="48", unit="HOURS", quote="Withdrawals are processed within 48 hours."
    )
    assert fns.evaluate_claim(claim, entry, DOCS)["result"] == "SUPPORTED"


def test_number_not_found_is_not_stated(fns):
    claim = number_claim(fns, "N | EQ | PERCENT | 0 | 0% deposit fee")
    r = fns.evaluate_claim(claim, number_entry(claim, found=False, value="", unit="", quote=""), DOCS)
    assert r["result"] == "NOT_STATED"
    assert (r["doc_value"], r["doc_unit"], r["quote"]) == ("", "", "")


def test_number_value_must_appear_in_the_quote(fns):
    claim = number_claim(fns, "N | EQ | PERCENT | 0 | 0% deposit fee")
    # the model reports 0 but quotes the line that says 0.3: it cannot flip the result
    entry = number_entry(claim, value="0", quote="The owner multisig may pause deposits at any time.")
    r = fns.evaluate_claim(claim, entry, DOCS)
    assert r["result"] == "UNCLEAR"


@pytest.mark.parametrize(
    "value,text,expected",
    [
        ("0", "Deposit fee: 0% today", True),
        ("0", "Deposit fee: 0.3% of every deposit.", False),  # a piece of 0.3
        ("3", "Deposit fee: 0.3%", False),  # the decimals of 0.3
        ("0.3", "Deposit fee: 0.3%.", True),
        ("1", "up to 1,000 users", False),  # a piece of 1,000
        ("000", "up to 1,000 users", False),
        ("10", "fee of 110 units", False),
        ("48", "processed within 48 hours.", True),
        ("5", "costs 5.", True),  # sentence-ending full stop is not a decimal point
        ("0", "10 or 0 or 20", True),  # a standalone match later in the text counts
        ("", "anything", False),
    ],
)
def test_number_in_text(fns, value, text, expected):
    assert fns.number_in_text(value, text) is expected


def test_number_substring_cannot_flip_a_contradiction(fns):
    claim = number_claim(fns, "N | EQ | PERCENT | 0 | 0% deposit fee")
    # the documentation says 0.3%; reporting "0" with that quote must not read as 0%
    entry = number_entry(claim, value="0", quote="Deposit fee: 0.3% of every deposit.")
    assert fns.evaluate_claim(claim, entry, DOCS)["result"] == "UNCLEAR"


def test_claim_value_must_be_a_whole_number_in_its_text(fns):
    assert fns.parse_claims("N | EQ | PERCENT | 0 | 0.5% fee") == (None, "BAD_NUMBER")
    assert fns.parse_claims("N | EQ | PERCENT | 5 | 0.5% fee") == (None, "BAD_NUMBER")


def test_number_with_ungrounded_quote_is_unclear(fns):
    claim = number_claim(fns, "N | EQ | PERCENT | 0 | 0% deposit fee")
    r = fns.evaluate_claim(claim, number_entry(claim, quote="Deposit fee: 0.3% on all assets."), DOCS)
    assert r["result"] == "UNCLEAR"


def test_number_with_bad_unit_or_value_is_unclear(fns):
    claim = number_claim(fns, "N | EQ | PERCENT | 0 | 0% deposit fee")
    assert fns.evaluate_claim(claim, number_entry(claim, unit="PARSECS"), DOCS)["result"] == "UNCLEAR"
    assert fns.evaluate_claim(claim, number_entry(claim, unit="DAYS"), DOCS)["result"] == "UNCLEAR"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: {k: v for k, v in e.items() if k != "unit"},
        lambda e: {**e, "extra": 1},
        lambda e: {**e, "found": "yes"},
        lambda e: {**e, "value": 3},
        lambda e: {**e, "id": 9},
    ],
)
def test_malformed_number_entry_is_none(fns, mutate):
    claim = number_claim(fns, "N | EQ | PERCENT | 0 | 0% deposit fee")
    assert fns.evaluate_claim(claim, mutate(number_entry(claim)), DOCS) is None


# ---------------------------------------------------------------- verdict


@pytest.mark.parametrize(
    "outcome,answers,expected",
    [
        ("OK", ["SUPPORTED"], "CLAIMS_HOLD"),
        ("OK", ["SUPPORTED", "SUPPORTED"], "CLAIMS_HOLD"),
        ("OK", ["CONTRADICTED"], "MISLEADING"),
        ("OK", ["SUPPORTED", "CONTRADICTED"], "MISLEADING"),
        ("OK", ["NOT_STATED", "CONTRADICTED", "UNCLEAR"], "MISLEADING"),
        ("OK", ["SUPPORTED", "NOT_STATED"], "UNVERIFIED"),
        ("OK", ["UNCLEAR"], "UNVERIFIED"),
        ("OK", [], "UNDETERMINED"),
        ("TOO_LARGE", [], "UNDETERMINED"),
        ("UNREADABLE", ["SUPPORTED"], "UNDETERMINED"),
    ],
)
def test_verdict_table(fns, outcome, answers, expected):
    results = [{"result": a} for a in answers]
    assert fns.verdict_from(outcome, results) == expected


def test_doubt_never_becomes_an_accusation(fns):
    for answers in (["UNCLEAR"], ["NOT_STATED"], ["SUPPORTED", "UNCLEAR"]):
        assert fns.verdict_from("OK", [{"result": a} for a in answers]) != "MISLEADING"


def test_bounds_view_is_consistent(fns):
    assert fns.MAX_CLAIMS == 8 and fns.MAX_ROUNDS == 3
    assert set(fns.UNITS) == {"PERCENT", "BPS", "DAYS", "HOURS", "MINUTES", "COUNT"}


# -------------------------------- leader_result_valid, rule by rule
# rounds_agree also compares the leader with the validator's own round, so some of
# these rules are reached a second time there; each is still pinned down on its own.

LRV_CLAIMS = "S | Audited by Hexa Labs || N | EQ | PERCENT | 0 | 0% deposit fee"
LRV_DOCS = "Audited by Hexa Labs in March.\n\nDeposit fee: 0.3% of every deposit.\n"


def lrv_good():
    return {
        "outcome": "OK",
        "reason": "",
        "results": [
            {"id": 0, "kind": "STATEMENT", "result": "SUPPORTED", "doc_value": "", "doc_unit": "",
             "quote": "Audited by Hexa Labs in March."},
            {"id": 1, "kind": "NUMBER", "result": "CONTRADICTED", "doc_value": "0.3", "doc_unit": "PERCENT",
             "quote": "Deposit fee: 0.3% of every deposit."},
        ],
    }


def lrv_set(**changes):
    """lrv_good() with fields of the first (s) or second (n) result replaced."""
    def build():
        r = lrv_good()
        for key, value in changes.items():
            index, field = (0, key[2:]) if key.startswith("s_") else (1, key[2:])
            r["results"][index][field] = value
        return r
    return build


LRV_BAD = {
    "unknown answer": lrv_set(s_result="MAYBE"),
    "kind mismatch": lrv_set(s_kind="NUMBER"),
    "boolean id": lrv_set(n_id=True),
    "ungrounded quote on a non-decisive result": lrv_set(s_result="UNCLEAR", s_quote="Nothing like this is written."),
    "decisive result with no quote": lrv_set(s_quote=""),
    "decisive result with an ungrounded quote": lrv_set(s_quote="Audited by somebody else."),
    "NOT_STATED with a quote": lrv_set(s_result="NOT_STATED"),
    "statement with a number": lrv_set(s_doc_value="1"),
    "number result that does not recompute": lrv_set(n_result="SUPPORTED"),
    "number result with an unusable unit": lrv_set(n_doc_unit="FURLONGS"),
    "number result with an unusable number": lrv_set(n_doc_value="0,3"),
    "reported number not in the quote": lrv_set(n_doc_value="0.30"),
    "undecided number result with a number": lrv_set(n_result="UNCLEAR"),
    "more results than claims": lambda: {**lrv_good(), "results": lrv_good()["results"] * 2},
    "fewer results than claims": lambda: {**lrv_good(), "results": lrv_good()["results"][:1]},
    "failed round that lists results": lambda: {**lrv_good(), "outcome": "BAD_CLAIM"},
    "extra key in a result": lambda: {**lrv_good(), "results": [{**lrv_good()["results"][0], "x": 1}, lrv_good()["results"][1]]},
    "not a dict": lambda: "nope",
    "results not a list": lambda: {"outcome": "OK", "reason": "", "results": "nope"},
}


def test_leader_result_valid_accepts_a_well_formed_result(fns):
    claims, _ = fns.parse_claims(LRV_CLAIMS)
    assert fns.leader_result_valid(lrv_good(), claims, LRV_DOCS) is True


def test_leader_result_valid_accepts_an_empty_failed_round(fns):
    claims, _ = fns.parse_claims(LRV_CLAIMS)
    failed = {"outcome": "BAD_CLAIM", "reason": "CLAIM_NOT_ON_PAGE", "results": []}
    assert fns.leader_result_valid(failed, claims, LRV_DOCS) is True


@pytest.mark.parametrize("name", sorted(LRV_BAD))
def test_leader_result_valid_rejects(fns, name):
    claims, _ = fns.parse_claims(LRV_CLAIMS)
    assert fns.leader_result_valid(LRV_BAD[name](), claims, LRV_DOCS) is False


# -------------------------------- gaps found by the mutation sweep


def test_eq_means_equal_not_at_most(fns):
    claim = {"op": "EQ", "unit": "PERCENT", "value": "1"}
    assert fns.number_result(claim, "0.3", "PERCENT") == "CONTRADICTED"
    assert fns.number_result(claim, "1", "PERCENT") == "SUPPORTED"
    assert fns.number_result(claim, "100", "BPS") == "SUPPORTED"
    assert fns.number_result(claim, "1.5", "PERCENT") == "CONTRADICTED"


def test_a_boolean_id_is_not_an_id(fns):
    claims, _ = fns.parse_claims("S | a || S | b")
    assert claims[1]["id"] == 1
    assert fns.evaluate_claim(claims[1], {"id": True, "answer": "NOT_STATED", "quote": ""}, DOCS) is None
    assert fns.evaluate_claim(claims[1], {"id": 1, "answer": "NOT_STATED", "quote": ""}, DOCS) is not None


def test_an_incomparable_number_is_stored_without_the_number(fns):
    """The docs give 48 HOURS for a PERCENT claim: UNCLEAR, and no number is recorded."""
    claims, _ = fns.parse_claims("N | EQ | PERCENT | 0 | 0% deposit fee")
    entry = {"id": 0, "found": True, "value": "48", "unit": "HOURS", "quote": "Withdrawals are processed within 48 hours."}
    result = fns.evaluate_claim(claims[0], entry, DOCS)
    assert result["result"] == "UNCLEAR"
    assert (result["doc_value"], result["doc_unit"], result["quote"]) == ("", "", "Withdrawals are processed within 48 hours.")
