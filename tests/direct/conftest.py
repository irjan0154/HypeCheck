"""Shared fixtures for the HypeCheck direct-mode suite.

`env` wires a deployed contract to a mocked marketing page, mocked documentation
and a mocked model, so every test reads as: serve the pages, propose, assess,
assert. All pages describe a fictional protocol; no real project is named.
"""

import hashlib
import json
import os
import re
import types

import pytest

CONTRACT = os.environ.get("HYPECHECK_CONTRACT", "contracts/hype_check.py")

MKT_URL = "https://pebblevault.example.com/home.txt"
DOC_URL = "https://pebblevault.example.com/docs.txt"


def doc(*paragraphs: str) -> str:
    return "\n\n".join(paragraphs) + "\n"


def sha(text) -> str:
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


MARKETING = doc(
    "Pebble Vault: yield without the fuss.",
    "Independently audited by Hexa Labs.",
    "No admin keys, ever.",
    "0% deposit fee.",
    "Withdraw within 72 hours.",
    "Deposits are insured by Seawall Mutual.",
)

DOCS = doc(
    "Pebble Vault documentation.",
    "The latest audit was performed by Hexa Labs in March.",
    "The owner multisig may pause deposits at any time.",
    "Deposit fee: 0.3% of every deposit.",
    "Withdrawals are processed within 48 hours.",
)

Q_AUDIT = "The latest audit was performed by Hexa Labs in March."
Q_PAUSE = "The owner multisig may pause deposits at any time."
Q_FEE = "Deposit fee: 0.3% of every deposit."
Q_WITHDRAW = "Withdrawals are processed within 48 hours."

C_AUDIT = "S | Independently audited by Hexa Labs"
C_KEYS = "S | No admin keys, ever"
C_FEE = "N | EQ | PERCENT | 0 | 0% deposit fee"
C_WITHDRAW = "N | LE | HOURS | 72 | Withdraw within 72 hours"
C_INSURED = "S | Deposits are insured by Seawall Mutual"

ALL_CLAIMS = "\n".join([C_AUDIT, C_KEYS, C_FEE, C_WITHDRAW])


def stmt(i, answer, quote=""):
    return {"id": i, "answer": answer, "quote": quote}


def num(i, value, unit, quote, found=True):
    return {"id": i, "found": found, "value": value, "unit": unit, "quote": quote}


# what an honest model answers for ALL_CLAIMS: audit holds, keys and fee are contradicted
HONEST = [
    stmt(0, "SUPPORTED", Q_AUDIT),
    stmt(1, "CONTRADICTED", Q_PAUSE),
    num(2, "0.3", "PERCENT", Q_FEE),
    num(3, "48", "HOURS", Q_WITHDRAW),
]


class Env:
    def __init__(self, vm, contract, fns, alice, bob):
        self.vm = vm
        self.c = contract
        self.fns = fns
        self.alice = alice
        self.bob = bob
        self.vm.sender = alice

    # -- pages -----------------------------------------------------------
    def serve(self, marketing=MARKETING, docs=DOCS, marketing_url=MKT_URL, docs_url=DOC_URL):
        for url, body in ((marketing_url, marketing), (docs_url, docs)):
            self.vm.mock_web(re.escape(url) + "$", {"status": 200, "body": body})

    def serve_status(self, url, status):
        self.vm.mock_web(re.escape(url) + "$", {"status": status, "body": "x"})

    def serve_bytes(self, url, data: bytes):
        self.vm.mock_web(
            re.escape(url) + "$",
            {"response": {"status": 200, "headers": {}, "body": data}, "method": "GET"},
        )

    def reset(self):
        self.vm.clear_mocks()

    # -- model -----------------------------------------------------------
    def model(self, entries=HONEST):
        self.vm.mock_llm(r".*", json.dumps({"items": entries}))

    def model_raw(self, raw: str):
        self.vm.mock_llm(r".*", raw)

    # -- contract --------------------------------------------------------
    def propose(self, claims=ALL_CLAIMS, marketing=MARKETING, docs=DOCS, label="Pebble Vault", sender=None):
        if sender is not None:
            self.vm.sender = sender
        return self.c.propose_check(label, MKT_URL, sha(marketing), DOC_URL, sha(docs), claims)

    def run(self, entries=HONEST, claims=ALL_CLAIMS, marketing=MARKETING, docs=DOCS):
        """Serve, mock the model, propose and assess. Returns the check id."""
        self.serve(marketing, docs)
        self.model(entries)
        cid = self.propose(claims, marketing, docs)
        self.c.assess(cid)
        return cid

    def info(self, cid):
        return self.c.get_check(cid)

    def results(self, cid):
        return json.loads(self.c.get_results(cid))

    def slots(self, who):
        """open_slots takes an Address; the direct_* fixtures are raw bytes."""
        return self.c.open_slots(self.fns.Address(who) if isinstance(who, (bytes, bytearray)) else who)

    def captured(self):
        return self.vm._captured_validators[-1][0]


@pytest.fixture
def fns(direct_vm, direct_deploy):
    """The contract module's globals, so pure helpers are tested directly."""
    contract = direct_deploy(CONTRACT)
    cls = type(contract._instance)
    return types.SimpleNamespace(**cls.__init__.__globals__)


@pytest.fixture
def env(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    cls = type(contract._instance)
    fns = types.SimpleNamespace(**cls.__init__.__globals__)
    return Env(direct_vm, contract, fns, direct_alice, direct_bob)
