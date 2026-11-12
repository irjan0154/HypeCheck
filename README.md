# HypeCheck

HypeCheck is a standalone GenLayer Intelligent Contract that reaches consensus on **whether the claims a project makes on its marketing page are supported by that project's own documentation**.

A proposer commits two pages (the marketing page and the documentation), each with the SHA-256 of its exact bytes, plus the claims to check. Every claim must appear word for word on the marketing page, and code checks that. Every validator then fetches both pages itself, verifies the commitments and asks its own model one bounded question per claim about the documentation. A number is never judged by the model: the model only reads the number the documentation states, and code compares it with the claim after normalising units. The verdict, its precedence rules and every bound are code. Other contracts read one typed answer: `is_misleading(id)`.

It is intentionally not a frontend, not a generic AI oracle and not an escrow. It records a small, auditable fact that other contracts can gate on.

> **Scope.** HypeCheck compares what a marketing page says with what the same project's documentation says. It does not say whether the documentation is true, whether a project is safe, or whether anyone acted unlawfully. It is not legal advice. All fixtures in this repository describe a fictional project.

## Release status

| Field | Value |
|---|---|
| Network | GenLayer Studio (studio.genlayer.com), mode "Normal (Full Consensus)" |
| Contract | `0x3421fE0FBfe6F53eC5326BB4C989A015448f456f` ([explorer](https://explorer-studio.genlayer.com/address/0x3421fE0FBfe6F53eC5326BB4C989A015448f456f)) |
| Live result | 6 of 6 labelled scenarios returned the expected verdict (one run each) |

The step-by-step deployment and live-run guide, and the full live record (including the mistakes made during the run), are in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). This table is filled in only from what was observed.

## The problem

Protocol pages promise things: "audited", "no admin keys", "0% fee", "withdraw within 72 hours", "insured". The documentation, a few clicks away, often says something slightly different: a 0.3% fee, an owner multisig that can pause deposits, no mention of insurance at all. Anything that depends on those promises (a wallet listing a vault, a DAO choosing where to deposit treasury funds, an insurer pricing cover) needs a neutral, reproducible answer to one question:

> Do the claims on the marketing page match what the project's own documentation says?

Today that answer comes from whoever reads both pages, and it cannot be re-checked on chain.

## Why GenLayer

| Instead of consensus | What goes wrong |
|---|---|
| A deterministic contract | It cannot fetch a web page, and "does this paragraph of documentation contradict that slogan" is a judgement about meaning, not a property of a byte string. |
| One reviewer or one LLM behind an API | The authority moves to whoever runs the endpoint and writes the prompt. The same capture, a different owner. |
| An ordinary oracle | An oracle reports values. This question is about meaning, before any value exists. |

### Delete GenLayer: what breaks?

The facts the verdict rests on are exactly the ones a deterministic contract cannot produce: *what do these two pages say* and *does this documentation sentence support, contradict or ignore that promise*. The first is made checkable by the committed SHA-256: every validator fetches the bytes itself, and a server that serves anything else is caught as `HASH_MISMATCH`. The second needs independent readers. With consensus, each validator runs its own model on the same claims and the same documentation and no single party chooses the answer.

### Why this is not a rejected pattern

- **Not a thin LLM wrapper.** The model answers one bounded question per claim from a closed vocabulary (`SUPPORTED`, `CONTRADICTED`, `NOT_STATED`, `UNCLEAR`). For numbers it does not answer at all: it reports the figure the documentation states, and code decides whether that figure satisfies the claim. The verdict and its precedence are code.
- **Not a format-only validator.** A validator re-fetches both pages, re-checks both hashes, re-checks that every claim is on the marketing page and re-asks its own model, then compares the stable decision fields. It rejects a leader that is well-formed and substantively false.
- **Not caller-authored evidence.** The proposer supplies addresses, hashes and claim texts, never the bytes. Validators fetch the bytes, and a claim that is not a verbatim excerpt of the committed marketing page is rejected by code before any model runs.
- **Not toy storage.** Checks carry a lifecycle with bounded retries and a per-proposer cap on work in flight that always releases.
- **Not a full application.** One contract, no frontend, no backend, no custody.
- **Not a generic "AI decides X".** The model's answer is grounded twice. A decisive answer needs a quote that is really an excerpt of the documentation, otherwise it becomes `UNCLEAR`. A number must appear as a whole number inside its quote, and the comparison is integer arithmetic in the contract. `UNCLEAR` and `NOT_STATED` can never become an accusation.

## Boundary: who owns what

| Step | Owner |
|---|---|
| Choosing which project and which claims to check, hosting the files, UI, notifications | Frontend or integrator |
| Committing URLs, hashes and claims; rules, bounds, lifecycle, slot accounting | Contract (deterministic) |
| Checking that each claim is on the marketing page | Contract (deterministic), on every validator |
| Fetching the bytes | Validators, each on its own, against the committed hash |
| Reading a statement claim against the documentation | Validators' models (non-deterministic) |
| Reading the figure a number claim is about | Validators' models (non-deterministic) |
| Comparing a figure with a number claim (units, `EQ` / `LE` / `GE`) | Contract (deterministic) |
| Verdict and `is_misleading` | Contract (deterministic) |
| Acting on the verdict (delisting, repricing, alerting) | Consuming contract or app |

Flow: `propose_check` → `assess` → leader fetches both pages, checks hashes, checks claims on the page, asks the model → validators repeat the whole round and compare → state is written after consensus → consumers read `is_misleading`.

## Claims

Claims are given as one string. Separate claims with a new line or, for one-line inputs such as Studio or the CLI, with ` || `.

```
S | <claim text>
N | <EQ|LE|GE> | <UNIT> | <number> | <claim text>
```

- `S` is a statement claim, for example `S | No admin keys, ever`.
- `N` is a number claim, for example `N | EQ | PERCENT | 0 | 0% deposit fee` or `N | LE | HOURS | 72 | Withdraw within 72 hours`. The documentation's number must equal (`EQ`), be at most (`LE`) or be at least (`GE`) the claimed number.
- The claim text must appear on the marketing page word for word (case and spacing insensitive), and a number claim's number must appear in its own text as a whole number.
- Units: `PERCENT`, `BPS` (rate), `DAYS`, `HOURS`, `MINUTES` (time), `COUNT`. Different groups never compare: they are `UNCLEAR`.
- Numbers are plain non-negative decimals with at most six decimal places. Integer arithmetic only, no floats.

## Verdicts

| Verdict | Meaning |
|---|---|
| `CLAIMS_HOLD` | Every claim is `SUPPORTED`. |
| `MISLEADING` | At least one claim is `CONTRADICTED` by the documentation. |
| `UNVERIFIED` | No contradiction, but at least one claim is `NOT_STATED` or `UNCLEAR`. |
| `UNDETERMINED` | The round did not assess the claims: a claim is not on the marketing page (`CLAIM_NOT_ON_PAGE`), or a page is too large or unreadable. |

`is_misleading(id)` is `True` only for an assessed `MISLEADING` check. Nothing that fails or is uncertain produces an accusation: wrongly saying "unverified" costs a re-read, wrongly saying "misleading" would harm a project.

The verdict covers **the claims that were listed**, not the page as a whole. `CLAIMS_HOLD` means those claims held, not that the project is honest.

## Lifecycle

```
propose_check ─► OPEN ──────────────── withdraw ──► WITHDRAWN
                  │
               assess
                  │
   ┌──────────────┼───────────────┐
hash mismatch  consensus ruled   error (reverts, nothing stored)
   │              │
RETRYABLE      ASSESSED
   │
after 3 rounds
   ▼
EXHAUSTED
```

`ASSESSED`, `EXHAUSTED` and `WITHDRAWN` release the proposer's slot (at most 5 checks in flight per proposer, so the allowance can never be used up permanently).

## Contract surface

Writes: `propose_check(label, marketing_url, marketing_sha256, docs_url, docs_sha256, claims)`, `assess(id)` (anyone may call it), `withdraw(id)`.

Views: `is_misleading`, `get_verdict`, `get_check`, `get_claims`, `get_results`, `open_slots`, `get_stats`, `bounds`.

Bounds: pages up to 40,000 bytes, up to 8 claims of up to 200 characters, quotes up to 200 characters, 3 rounds, 5 checks in flight per proposer.

## Consensus

There is exactly one non-deterministic round per `assess`, run by the leader and again by every validator. [`docs/CONSENSUS.md`](docs/CONSENSUS.md) states the rule in full; in short:

| Validators must agree on | Validators may differ on |
|---|---|
| The round outcome and reason | The quote (it must still be a real excerpt of the documentation the validator fetched itself) |
| The result of every claim | How a number is written (`0.3` PERCENT and `30` BPS are the same number) |
| For a decisive number result, the number read from the documentation, after unit normalisation | Anything the contract does not store as a decision |

Failure paths follow the GenLayer error classes:

| Class | When | Agreement |
|---|---|---|
| `[EXPECTED]` | A business rule was violated (bad URL, bad hash, bad claim, cap reached) | Exact match |
| `[EXTERNAL]` | A source answered 4xx or a redirect | Exact match |
| `[TRANSIENT]` | Network failure or 5xx | Agree if both are transient |
| `[LLM_ERROR]` | The model failed or returned malformed output | Validators always disagree, which forces a new leader. Nothing is stored. |

A fetched page that does not match its committed hash is not an error: it is recorded as a bounded `RETRY` and ends as `EXHAUSTED` after three rounds.

## Reading the verdict from another contract

```python
hype = gl.get_contract_at(Address(hype_check_address))
if hype.view().is_misleading(check_id):
    ...  # for example: refuse to list the vault, raise a risk score, flag for review
```

HypeCheck does not execute anything on its own and holds no funds.

## Verification

Everything below was run against the source in this repository.

| Gate | Result | How to reproduce |
|---|---|---|
| Direct Mode suite | 300 passed | `python -m pytest -q` |
| GenVM lint | passed (3 checks) | `genvm-lint check contracts/hype_check.py` |
| GenVM check | 11 methods (8 view, 3 write) | same command |
| Mutation sweep | 102 of 106 mutants killed, 4 equivalent by construction, 0 survived | `python scripts/mutate.py` |

A green suite shows the contract passes its tests, not that the tests would notice a deleted guard. The mutation sweep removes or reverses one rule at a time (the validator's comparison, the hash check, the claim-on-page check, quote grounding, whole-number matching, unit factors, comparison operators, verdict precedence, slot release, error-class handling and others) and reruns the whole suite. It found two real gaps (a leader error of the wrong class being accepted next to a transient validator error, and the comparison fallback for an unknown operator), which now have their own tests. Each equivalent mutant carries a written argument in `scripts/mutate.py`.

What Direct Mode does **not** cover, and what the live run is for: real multi-validator consensus with different models, real model answers and closure serialisation under `run_nondet_unsafe`. The six live scenarios ran on Studio and each `assess` ended `ASSESSED` in one round; they show the contract works end to end, but they are one run each and do not measure how stable the models' answers are across many runs, nor whether independent models split between `CONTRADICTED`, `NOT_STATED` and `UNCLEAR` on subtler claims.

## Limitations

- **The model can be wrong.** A statement result is a judgement. The contract limits the damage (grounded quotes, numbers compared by code, doubt fails closed, validators compare results) but cannot make a judgement correct.
- **Four results can split honest models.** Two honest models may answer `NOT_STATED` and `UNCLEAR` for the same claim. Validators must agree on the result, so such a claim may cost extra rounds. Short, concrete claims reduce this.
- **The proposer picks the claims.** The verdict covers the listed claims only. A proposer can list only claims that hold, so read `get_claims` before relying on `CLAIMS_HOLD`.
- **Numbers are narrow.** Integers and plain decimals only. A figure written with separators (`1,000`) is treated as unclear, never as a contradiction. Currencies and compound figures are not supported.
- **Plain text only.** Bytes are decoded as UTF-8. HTML or PDF would be read as markup or fail to decode. Publish a plain-text or Markdown copy of each page.
- **Commitments, not truth.** The hash proves that two pages are the ones the proposer named. It does not prove they are the live pages of any project, or that the documentation is accurate.
- **URL admission is not complete SSRF prevention.** The contract rejects non-HTTPS, credentials, IP literals, local and internal names and odd ports. It cannot see DNS resolution or redirects from contract code.
- **Size limits are enforced after the response arrives**, because the runtime does not expose a trusted pre-fetch byte limit.
- **A claim text may not contain `||`**, which separates claims on one line.
- **English-language pages only** were exercised.
- **Not legal advice**, and no real project is evaluated by this repository.

## Repository layout

```
contracts/hype_check.py        the one deployable contract
tests/direct/                  Direct Mode suite (pure logic, contract flow, validator, fixtures)
fixtures/                      fictional pages and manifest.json (hashes, expected answers)
scripts/mutate.py              mutation sweep
scripts/make_manifest.py       builds fixtures/manifest.json (and manifest.live.json with --base-url)
scripts/print_live_commands.py prints the CLI commands for the six live scenarios
docs/                          consensus rule, security notes, deployment and live-run guide
```

## Reviewer fast path

1. [`docs/CONSENSUS.md`](docs/CONSENSUS.md): what must agree and why.
2. [`contracts/hype_check.py`](contracts/hype_check.py): start at `verdict_from`, then `evaluate_claim` (the grounding gate and the number comparison), then `_round`, `rounds_agree` and `assess`.
3. [`tests/direct/test_validator.py`](tests/direct/test_validator.py): whether the contract has a validator or only a shape check.
4. [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): the deployment guide and the live evidence (contract address, scenarios, observed results).

## Development

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
genvm-lint check contracts/hype_check.py
python scripts/mutate.py
```
