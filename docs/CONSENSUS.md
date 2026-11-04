# Consensus rule

This document states exactly what HypeCheck's validators must agree on, what they may differ on, and why. The code is `rounds_agree`, `leader_result_valid`, `errors_agree` and `_handle_leader_error` in [`contracts/hype_check.py`](../contracts/hype_check.py); the behaviour is pinned by [`tests/direct/test_validator.py`](../tests/direct/test_validator.py).

## The round

`assess(id)` runs exactly one non-deterministic block with `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`. `leader_fn` calls `_round`:

1. Fetch the marketing page. Check size, then SHA-256 against the commitment, then UTF-8.
2. Do the same for the documentation page. (If step 1 already produced a recorded failure, the documentation is not fetched. Every node follows the same order, so this is deterministic.)
3. Check that every claim occurs on the marketing page. If one does not, record `BAD_CLAIM` and stop. The model is not called.
4. Otherwise ask the model one bounded question per claim, parse the answer strictly, ground every quote and compare every number with code.

All state changes happen after consensus, outside the block. The block never touches storage.

## What a round produces

A round returns `{outcome, reason, results}`.

| outcome | reason | When | Stored as |
|---|---|---|---|
| `OK` | _(empty)_ | All claims answered. `results` has one entry per claim. | `ASSESSED`, verdict from the results |
| `RETRY` | `HASH_MISMATCH_MARKETING` or `HASH_MISMATCH_DOCS` | Fetched bytes differ from the committed SHA-256 | `RETRYABLE`; `EXHAUSTED` on the third round |
| `TOO_LARGE` | `DOC_SIZE_MARKETING` or `DOC_SIZE_DOCS` | Empty body, or over 40,000 bytes | `ASSESSED`, `UNDETERMINED` |
| `UNREADABLE` | `BAD_ENCODING_MARKETING` or `BAD_ENCODING_DOCS` | Bytes are not valid UTF-8 | `ASSESSED`, `UNDETERMINED` |
| `BAD_CLAIM` | `CLAIM_NOT_ON_PAGE` | A claim is not on the committed marketing page | `ASSESSED`, `UNDETERMINED` |

Each `results` entry is `{id, kind, result, doc_value, doc_unit, quote}`, where `result` is one of `SUPPORTED`, `CONTRADICTED`, `NOT_STATED`, `UNCLEAR`.

## How one claim becomes a result

**Statement claim.** The model answers `SUPPORTED`, `CONTRADICTED`, `NOT_STATED` or `UNCLEAR` and gives a quote. A `SUPPORTED` or `CONTRADICTED` answer whose quote is not a real excerpt of the documentation (case and spacing insensitive, at most 200 characters) becomes `UNCLEAR`.

**Number claim.** The model never compares. It reports `found`, `value`, `unit` and a quote. The contract then requires that the quote is a real excerpt of the documentation and that `value` appears in it as a whole number (`0` is not found inside `0.3` or `10`). If so, it normalises both numbers to a base unit with integer arithmetic (`PERCENT` is 100 basis points, a day is 1440 minutes, and so on) and applies `EQ`, `LE` or `GE`. A unit from another group, or anything unparsable, is `UNCLEAR`. `found: false` is `NOT_STATED`.

## What a validator does

When the leader returned a value:

1. Re-run the whole round (`_round`) with its own fetches and its own model.
2. If that raises a classified error, **disagree**. The leader produced something this validator could not reproduce.
3. Otherwise accept only if `rounds_agree(leader, mine, claims, docs_text)` holds, where `docs_text` is the documentation this validator fetched itself.

When the leader raised an error, `_handle_leader_error` re-runs the round: if it succeeds, **disagree** (the leader is the odd one out); if it raises a classified error, apply `errors_agree`; any unclassified exception means **disagree**.

## `rounds_agree`: must agree

| Field | Rule |
|---|---|
| `outcome` and `reason` | Equal |
| Number of `results` | Equal |
| `id` and `result` of every claim | Equal |
| For a number claim whose result is `SUPPORTED` or `CONTRADICTED`: the number read from the documentation | Equal after unit normalisation (`0.3` PERCENT equals `30` BPS) |

The claims themselves are committed on chain and the pages are bound to their hashes, so every honest node starts from the same inputs. The only freedom left is the model's reading, and that is what has to agree.

## `rounds_agree`: may differ, but must be valid

The `quote`, and how a number is written, are not compared with the validator's own answer, because two honest models can quote different sentences of the same documentation. They are still **stored**, so they are held to deterministic rules by `leader_result_valid`, which every validator applies to the leader's result:

- results line up one to one with the claims (same `id`, same `kind`), with exactly the keys `id, kind, result, doc_value, doc_unit, quote`;
- `result` is in the vocabulary and every field is a string where a string is expected;
- a non-empty `quote` is a real excerpt of the documentation **this validator fetched itself**, at most 200 characters;
- a `SUPPORTED` or `CONTRADICTED` result has a grounded quote;
- a `NOT_STATED` result carries no quote and no number;
- a statement result carries no number;
- a decisive number result has a usable number and unit, the number appears as a whole number in the quote, and **recomputing** the comparison from that number gives the leader's result;
- an undecided number result carries no number;
- a round that did not end `OK` carries no results.

Without this a leader could agree with the validators on every result and still store an invented quote or a number the documentation never states.

## What is not compared, and why

| Not compared | Reason |
|---|---|
| Model wording beyond the fixed fields | The model has no free-text field. The prompt asks for fixed keys, and anything else fails the strict parse. |
| Latency, byte counts, raw model output | Never used to decide anything. |
| The leader's verdict | The leader never sends one. The verdict is computed after consensus by `verdict_from` from the agreed results. |

## Failure paths

| Class | Raised as | Agreement |
|---|---|---|
| `[EXPECTED]` | `[EXPECTED] BAD_URL`, `BAD_CLAIM`, `NOT_ASSESSABLE`, and so on | Exact message match |
| `[EXTERNAL]` | `[EXTERNAL] HTTP <status>` for any non-200, non-5xx answer (404, 403, redirects) | Exact message match |
| `[TRANSIENT]` | `[TRANSIENT] fetch failed`, `[TRANSIENT] source unavailable` (5xx) | Agree if both sides are transient |
| `[LLM_ERROR]` | `[LLM_ERROR] model call failed`, `[LLM_ERROR] malformed model output` | Never agree. This forces a new leader; nothing is stored. |

A hash mismatch is deliberately **not** an error. It is an agreed, recorded fact ("the bytes served do not match the commitment"), bounded to three rounds. Validators agree on it only if they see it too; a validator that fetched the committed bytes disagrees.

## Worked examples

**Honest leader.** The leader and every validator fetch the same bytes (the hash guarantees it), find every claim on the marketing page, and ask their own models. Quotes differ; results match; the result is accepted.

**Leader flips a result.** It reports `SUPPORTED` for a fee claim the documentation contradicts. Validators' own models, and the code comparison behind them, say `CONTRADICTED`; the results differ; disagree.

**Leader keeps the result but forges the number.** It reports the documentation's fee as `0` with a quote that says `0.3%`. The number is not in the quote as a whole number, so `leader_result_valid` fails; disagree. If it forges a unit instead (`0.3` as BPS, to make a `LE` claim hold), the validators' normalised numbers differ; disagree.

**Leader stores an invented quote.** Results match, but `leader_result_valid` fails because the quote is not in the documentation this validator fetched; disagree.

**Leader judges a claim that is not on the page.** Every validator runs the same check against the committed marketing page and records `BAD_CLAIM`; a leader that went on to call the model disagrees on outcome and reason.

**Leader's model hallucinates.** It raises `[LLM_ERROR]`. Validators never agree on that, a new leader is chosen, and the check stays `OPEN` with nothing stored.

**The server serves different bytes to different nodes.** A node that is served bytes other than the committed ones records `HASH_MISMATCH_*`. It can agree only with nodes that saw the same mismatch; a node that saw the committed bytes disagrees.

## Assumptions and limits

- **Diverse models.** The scheme relies on validators running different models, so that one model's blind spot is not shared by a majority. If most validators ran the same model, agreement would be cheap and less informative.
- **The model can be wrong consistently.** Agreement shows that independent readers reached the same result, not that the result is right.
- **`NOT_STATED` versus `UNCLEAR` can split honest models.** Both are "no decision", but validators must agree on the exact result. A claim on which models split costs extra rounds. This is a design trade-off: collapsing the two would lose the difference between "the documentation is silent" and "the documentation is ambiguous". How often it happens on real models is not known until a live run measures it.
- **Direct Mode does not run real multi-validator consensus.** It replays one validator function against mocked data (`run_validator`), which pins the comparison logic. Real consensus with real models is exercised only by a live run recorded in [`DEPLOYMENT.md`](DEPLOYMENT.md), and none is recorded yet.
- **Appeals and leader rotation** are GenLayer protocol behaviour and are not reimplemented here.
