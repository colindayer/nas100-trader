"""strategy_contract.py -- PHASE 601 Stage 2. A strategy may not trade unless a frozen, approved
StrategyContract exists for it. No existing strategy is auto-approved. Fail closed: unknown => no trade.
"""
from __future__ import annotations
import glob, hashlib, json, os
from dataclasses import dataclass, field, asdict

STATUSES = ["RESEARCH_ONLY", "DISCOVERY", "NEEDS_REPLICATION",
            "PAPER_APPROVED", "LIVE_APPROVED", "SUSPENDED", "RETIRED"]
CONTRACT_DIR = "strategy_contracts"

# V-03: fields whose alteration changes what a strategy is ALLOWED to do. A contract whose hash
# does not cover these is untrusted. Editing any of them on disk invalidates the signature.
SIGNED_FIELDS = ["strategy_id", "version", "code_commit", "status", "approved_trial_ids",
                 "permitted_symbols", "maximum_risk_per_trade", "maximum_concurrent_positions",
                 "pyramiding_allowed", "approval_actor", "approval_timestamp"]
SIGNING_KEY_ENV = "CONTRACT_SIGNING_KEY"      # optional shared secret -> HMAC instead of plain hash


def content_hash(d: dict) -> str:
    """Digest over the governance-critical fields only."""
    body = json.dumps({k: d.get(k) for k in SIGNED_FIELDS}, sort_keys=True,
                      separators=(",", ":")).encode()
    key = os.environ.get(SIGNING_KEY_ENV)
    if key:
        import hmac
        return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()[:32]
    return hashlib.sha256(body).hexdigest()[:32]


@dataclass
class StrategyContract:
    strategy_id: str
    strategy_name: str
    strategy_family: str
    version: str                       # frozen code version this contract authorizes
    code_commit: str
    status: str = "RESEARCH_ONLY"      # conservative default -- nothing trades by default
    approved_trial_ids: list = field(default_factory=list)
    dataset_fingerprint: str = ""
    feature_version: str = ""
    model_version: str = ""
    permitted_symbols: list = field(default_factory=list)
    permitted_timeframes: list = field(default_factory=list)
    permitted_sessions: list = field(default_factory=list)
    entry_function: str = ""
    exit_function: str = ""
    stop_function: str = ""
    position_sizing_function: str = ""
    maximum_risk_per_trade: float = 0.0
    maximum_symbol_exposure: float = 0.0
    maximum_portfolio_exposure: float = 0.0
    maximum_concurrent_positions: int = 0
    pyramiding_allowed: bool = False
    maximum_entries_per_symbol: int = 1
    cost_model: str = ""
    expected_trade_frequency: str = ""
    validation_start: str = ""
    validation_end: str = ""
    approval_timestamp: str = ""
    approval_actor: str = ""
    expiration_timestamp: str = ""
    content_hash: str = ""                      # V-03 signature over SIGNED_FIELDS
    signature_valid: bool = False               # runtime only; never trusted from disk

    def __post_init__(self):
        assert self.status in STATUSES, f"bad status {self.status}"

    def sign(self) -> str:
        d = asdict(self)
        d.pop("content_hash", None); d.pop("signature_valid", None)
        self.content_hash = content_hash(d)
        return self.content_hash

    def verify(self) -> bool:
        if not self.content_hash:
            return False
        d = asdict(self)
        d.pop("content_hash", None); d.pop("signature_valid", None)
        return content_hash(d) == self.content_hash

    def may_trade_demo(self) -> bool:
        # V-03: an unsigned or tampered contract cannot authorise anything, whatever it claims.
        return self.status == "PAPER_APPROVED" and self.signature_valid

    def may_trade_real(self) -> bool:
        return self.status == "LIVE_APPROVED" and self.signature_valid


class StrategyRegistry:
    """Loads contracts from strategy_contracts/*.json. Absence => fail closed."""
    def __init__(self, path=CONTRACT_DIR):
        self.path = path
        self.contracts: dict[str, StrategyContract] = {}
        self.load()

    def load(self):
        """Load and VERIFY. An unsigned/tampered contract is downgraded to RESEARCH_ONLY in
        memory (fail closed) and recorded in self.rejected -- never silently trusted."""
        self.rejected = []
        for f in glob.glob(os.path.join(self.path, "*.json")):
            try:
                d = json.load(open(f))
            except Exception as e:
                self.rejected.append({"file": os.path.basename(f), "reason": f"UNREADABLE: {e}"})
                continue
            d.pop("signature_valid", None)
            try:
                c = StrategyContract(**d)
            except Exception as e:
                self.rejected.append({"file": os.path.basename(f), "reason": f"INVALID: {e}"})
                continue
            c.signature_valid = c.verify()
            if not c.signature_valid:
                self.rejected.append({"file": os.path.basename(f), "strategy_id": c.strategy_id,
                                      "claimed_status": c.status,
                                      "reason": "UNSIGNED" if not c.content_hash else "SIGNATURE_MISMATCH"})
                c.status = "RESEARCH_ONLY"          # fail closed
            self.contracts[c.strategy_id] = c

    def get(self, strategy_id: str) -> StrategyContract | None:
        return self.contracts.get(strategy_id)      # None => caller must fail closed

    def save(self, c: StrategyContract, sign: bool = True):
        """Saving SIGNS by default. An out-of-band disk edit will not match the signature."""
        os.makedirs(self.path, exist_ok=True)
        if sign:
            c.sign()
        d = asdict(c); d.pop("signature_valid", None)
        json.dump(d, open(os.path.join(self.path, f"{c.strategy_id}.json"), "w"), indent=1)
        c.signature_valid = c.verify()
        self.contracts[c.strategy_id] = c
