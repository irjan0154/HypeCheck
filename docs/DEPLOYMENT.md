# Deployment and live run

This file is both the guide and the record. The guide comes first. The **Live record** at the bottom stays empty until a real run fills it in, and nothing else in the repository claims live results.

## Prerequisites

- A public GitHub repository containing this project
- Python 3.12 or newer for the checks: `pip install -r requirements.txt`
- Either GenLayer Studio in the browser (studio.genlayer.com) or the CLI: `npm install -g genlayer`

StudioNet is gasless, so a zero GEN balance is normal and no faucet is needed. StudioNet is rate limited per IP (about 60 requests a minute), so run the scenarios one after another and wait for each result.

## 1. Check the source locally

```
python -m pytest -q
genvm-lint check contracts/hype_check.py
sha256sum contracts/hype_check.py          # record this value below
```

Expected: all tests pass; lint passes; 11 methods (8 view, 3 write).

## 2. Publish the fixtures at stable raw URLs

The contract fetches each page and checks its SHA-256, so the files must be served **byte for byte** as committed. `.gitattributes` pins line endings to LF.

1. Commit and push everything (upload folders one by one if you use the GitHub web page, which skips folders in a mixed drag). Note the full commit hash `<commit>` that contains `fixtures/`.
2. Check that the raw files match the manifest (this is the check that prevents `HASH_MISMATCH`):

   ```
   curl -s https://raw.githubusercontent.com/<user>/<repo>/<commit>/fixtures/pebble-home.txt | sha256sum
   ```

   Compare with `marketing_sha256` in `fixtures/manifest.json`. Repeat for each `pebble-docs-*.txt` against `docs_sha256`.
3. Build the manifest with absolute URLs, pinned to that commit:

   ```
   python scripts/make_manifest.py --base-url https://raw.githubusercontent.com/<user>/<repo>/<commit>/fixtures
   ```

   This writes `fixtures/manifest.live.json`. Commit it afterwards. The URLs stay valid because they point at the earlier commit.

## 3. Deploy

In Studio: paste `contracts/hype_check.py` into a new contract file, run it in "Normal (Full Consensus)" mode and press Deploy. The constructor takes no arguments.

With the CLI:

```
genlayer network set studionet
genlayer account create --name hypecheck        # first time only
genlayer deploy --contract contracts/hype_check.py
```

Note the **transaction hash** and the **contract address**.

Lifecycle status is not execution success: a failed deploy can still reach `ACCEPTED` or `FINALIZED` with no contract created. Always read the receipt (`genlayer receipt <deployTxHash> --stdout --stderr`, or the GenVM result in the explorer). Then confirm the deployment is what you intend: the methods list shows 11 methods, and the code shown by the explorer matches `contracts/hype_check.py`.

Open `https://explorer-studio.genlayer.com/address/<address>` and check the transaction shows a finalized, successful result.

## 4. Run the six scenarios

```
python scripts/print_live_commands.py <address>
```

This prints, for each scenario, the four commands to run in order: `propose_check`, `assess`, `get_check`, `get_results`. In Studio, call the same methods with the same arguments: the `claims` argument is a single line with ` || ` between claims, exactly as printed. Run the blocks in the order printed, on a fresh deployment, so check ids are 1 to 6. Each block assesses its check before the next is proposed (a proposer may have at most 5 in flight).

| # | Scenario | Expected verdict | Expected per-claim results | Why it is in the set |
|---|---|---|---|---|
| 1 | `holds` | `CLAIMS_HOLD` | audit, keys, fee, withdraw, insured: all `SUPPORTED` | the honest case, both claim kinds |
| 2 | `fee-lie` | `MISLEADING` | audit `SUPPORTED`, fee `CONTRADICTED` (docs say 0.3%), withdraw `SUPPORTED` (48 h is within 72 h) | a number contradiction found by code |
| 3 | `keys-lie` | `MISLEADING` | keys `CONTRADICTED` (owner multisig), fee `SUPPORTED` | a statement contradiction |
| 4 | `unverified` | `UNVERIFIED` | audit `SUPPORTED`, insured `NOT_STATED` | silence is not an accusation |
| 5 | `injection` | `MISLEADING` | fee `CONTRADICTED`, withdraw `SUPPORTED` | an injection sentence inside the documentation must not change the verdict |
| 6 | `invented` | `UNDETERMINED`, reason `CLAIM_NOT_ON_PAGE` | none; the model is not called | a claim the page never made is refused |

The labelled results, the deciding sentence of the documentation for every claim and the figure it states are in `fixtures/manifest.json` (`expected_results`).

## 5. Record what happened

For every scenario record the transaction hash, the validators' votes shown in the explorer, `status`, `verdict`, `reason`, `rounds`, and each claim's `result`, `doc_value`, `doc_unit` and `quote`. **Record disagreements and failures as they happened.** A reverted `assess` (`[LLM_ERROR]`, `[TRANSIENT]`, `[EXTERNAL]`) is a normal outcome of the design: nothing is stored and the call can be repeated. A verdict that differs from the label is a finding about the model, not a reason to edit the label afterwards. Also read `get_stats`, `is_misleading` for ids 2, 3 and 5, and `open_slots` for the proposer.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `status` is `RETRYABLE` with reason `HASH_MISMATCH_MARKETING` or `_DOCS` | The served bytes differ from the manifest. Re-run the `curl | sha256sum` check; look for line-ending or trailing-newline changes. |
| `assess` reverts with `[EXTERNAL] HTTP 404` | Wrong URL, or the commit is not pushed yet. |
| `assess` reverts with `[LLM_ERROR]` | The model failed or answered badly. Nothing was stored; call `assess` again. |
| `assess` reverts with `[TRANSIENT]` | Network or server error on the source. Call `assess` again. |
| `assess` never settles on a verdict for one scenario | Validators may be splitting between two results for a claim (for example `NOT_STATED` and `UNCLEAR`). Record it; it is a finding. |
| HTTP 429 or `-32429` from the CLI | StudioNet rate limit. Wait a minute and continue. |
| Deploy receipt shows an execution error | Fix the error first. Missing code or schema is expected after a failed deploy. |
| `propose_check` reverts with `[EXPECTED] BAD_URL` | The URL is not plain HTTPS on port 443, or contains credentials, an IP address or an internal name. |
| `propose_check` reverts with `[EXPECTED] BAD_CLAIM` or `BAD_NUMBER` | The claims string is malformed: each claim starts with `S |` or `N |`, a number claim needs `N | <EQ/LE/GE> | <UNIT> | <number> | <text>`, and its number must appear in its own text. |
| Studio shows an old value after `assess` | Studio reads can be stale; refresh and read again. |

## Live record

**No live run has been recorded yet.** Everything below is to be filled in from a real run, and left empty until then.

### Deployment

| Field | Value |
|---|---|
| Network | |
| Contract address | |
| Deployment result | |
| Deployer / proposer account | |
| Source SHA-256 (file in this repository) | |
| Source parity | |
| Fixtures commit | |
| Methods shown by Studio | |

### Scenarios

| # | Scenario | Expected | Observed `status` / `verdict` / `reason` / `rounds` | Observed results per claim |
|---|---|---|---|---|
| 1 | holds | `CLAIMS_HOLD` | | |
| 2 | fee-lie | `MISLEADING` | | |
| 3 | keys-lie | `MISLEADING` | | |
| 4 | unverified | `UNVERIFIED` | | |
| 5 | injection | `MISLEADING` | | |
| 6 | invented | `UNDETERMINED` / `CLAIM_NOT_ON_PAGE` | | |

### What this run does and does not show

To be written after the run, from what was actually observed.
