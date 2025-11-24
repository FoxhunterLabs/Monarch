"""
Agnostic Autonomy Kernel v0.1
- Tick-based deterministic-ish core
- Pluggable modules for perception, risk, policy, governance, actuation
- No domain-specific physics baked in

Drop this into Replit as app.py and run `python app.py`.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Dict, Any, List, Protocol, Optional
import time
import uuid
import hashlib
import json
import random


# =========================
# 1. Core data models
# =========================

TickId = int


class RiskLevel(Enum):
    STABLE = auto()
    ELEVATED = auto()
    HIGH = auto()
    CRITICAL = auto()


class ProposalStatus(Enum):
    PENDING = auto()
    AUTO_APPROVED = auto()
    REQUIRES_HUMAN = auto()
    BLOCKED = auto()


@dataclass
class SensorFrame:
    """Raw inputs from the outside world for a single tick."""
    tick: TickId
    ts: float
    streams: Dict[str, Any]  # e.g. {"imu": {...}, "fleet": [...], "ops": {...}}


@dataclass
class WorldState:
    """Semantic understanding of current situation."""
    tick: TickId
    ts: float
    facts: Dict[str, Any]      # tracks, objects, status
    health: Dict[str, float]   # 0–1 per subsystem


@dataclass
class RiskReport:
    tick: TickId
    ts: float
    score: float               # 0–100
    level: RiskLevel
    clarity: float             # 0–100
    drivers: Dict[str, float]  # name -> contribution
    notes: str = ""


@dataclass
class Intent:
    """High-level behavior intent, domain-agnostic."""
    id: str
    kind: str                  # e.g. "HOLD", "RETREAT", "SLOW_ROLL"
    priority: int              # higher = more important
    params: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass
class Proposal:
    """Concrete proposed change to the system."""
    id: str
    tick: TickId
    source_intent: str
    action: str                # human-readable action label
    bounds: Dict[str, Any]     # envelope / constraints
    expected_effect: Dict[str, Any]
    status: ProposalStatus = ProposalStatus.PENDING
    governance_notes: str = ""


@dataclass
class Decision:
    id: str
    proposal_id: str
    tick: TickId
    status: ProposalStatus
    operator: str              # "AUTO" or human id
    comment: str = ""


@dataclass
class ActuationCommand:
    """What an external actuator layer would consume."""
    id: str
    tick: TickId
    channel: str               # e.g. "vehicle", "fleet", "alerts"
    payload: Dict[str, Any]


@dataclass
class AuditEntry:
    id: str
    tick: TickId
    ts: float
    kind: str
    payload: Dict[str, Any]
    prev_hash: str
    hash: str


@dataclass
class GovernanceConfig:
    """Human / safety envelope knobs."""
    max_auto_risk: float = 40.0       # above this, always require human
    hard_block_risk: float = 80.0     # above this, block proposals
    require_human_for: List[str] = field(default_factory=lambda: ["RETREAT", "EMERGENCY"])
    gate_open: bool = False           # human gate switch


@dataclass
class TickResult:
    """Snapshot of a full kernel cycle for external use / UI."""
    tick: TickId
    sensor_frame: SensorFrame
    world: WorldState
    risk: RiskReport
    intents: List[Intent]
    proposals: List[Proposal]
    decisions: List[Decision]
    actuation: List[ActuationCommand]
    audit_entries: List[AuditEntry]


# =========================
# 2. Plugin interfaces
# =========================

class SensorAdapter(Protocol):
    def read(self, tick: TickId, prev_world: Optional[WorldState]) -> SensorFrame:
        ...


class PerceptionModule(Protocol):
    def run(self, frame: SensorFrame, prev_world: Optional[WorldState]) -> WorldState:
        ...


class RiskModule(Protocol):
    def run(self, world: WorldState) -> RiskReport:
        ...


class PolicyModule(Protocol):
    def run(self, world: WorldState, risk: RiskReport) -> List[Intent]:
        ...


class ProposalModule(Protocol):
    def run(self, intents: List[Intent],
            world: WorldState,
            risk: RiskReport) -> List[Proposal]:
        ...


class GovernanceModule(Protocol):
    def run(self,
            proposals: List[Proposal],
            world: WorldState,
            risk: RiskReport,
            config: GovernanceConfig) -> List[Decision]:
        ...


class ActuationModule(Protocol):
    def run(self, decisions: List[Decision],
            world: WorldState) -> List[ActuationCommand]:
        ...


# =========================
# 3. Helpers
# =========================

def sha256(data: Dict[str, Any]) -> str:
    s = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# =========================
# 4. Default modules
# =========================

class SyntheticSensorAdapter:
    """
    Tiny deterministic-ish synthetic adapter so the kernel runs
    even without real hardware.
    """
    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)

    def read(self, tick: TickId, prev_world: Optional[WorldState]) -> SensorFrame:
        ts = time.time()
        # Toy signals
        base_load = 0.4 + 0.2 * self.rng.random()
        env_stress = 0.3 + 0.3 * self.rng.random()
        comms_ok = 0.7 + 0.3 * self.rng.random()

        streams = {
            "ops": {
                "system_load": base_load,
                "env_stress": env_stress,
                "comms_quality": comms_ok,
            }
        }
        return SensorFrame(tick=tick, ts=ts, streams=streams)


class DefaultPerceptionModule:
    def run(self, frame: SensorFrame, prev_world: Optional[WorldState]) -> WorldState:
        ops = frame.streams.get("ops", {})
        # Health metrics 0–1
        health = {
            "compute": max(0.0, 1.0 - ops.get("system_load", 0.5)),
            "environment": max(0.0, 1.0 - ops.get("env_stress", 0.5)),
            "comms": ops.get("comms_quality", 0.8),
        }
        facts = {
            "raw_ops": ops,
            "alerts": [],
        }
        return WorldState(
            tick=frame.tick,
            ts=frame.ts,
            facts=facts,
            health=health,
        )


class DefaultRiskModule:
    def run(self, world: WorldState) -> RiskReport:
        h = world.health
        # lower health → higher risk
        compute_r = 1.0 - h.get("compute", 0.8)
        env_r = 1.0 - h.get("environment", 0.8)
        comms_r = 1.0 - h.get("comms", 0.8)

        score = 100.0 * (0.35 * compute_r + 0.40 * env_r + 0.25 * comms_r)
        score = max(0.0, min(100.0, score))

        if score < 25:
            level = RiskLevel.STABLE
        elif score < 50:
            level = RiskLevel.ELEVATED
        elif score < 75:
            level = RiskLevel.HIGH
        else:
            level = RiskLevel.CRITICAL

        # clarity drops as risk goes up
        clarity = max(30.0, 100.0 - score * 0.6)

        drivers = {
            "compute": round(compute_r * 100, 1),
            "environment": round(env_r * 100, 1),
            "comms": round(comms_r * 100, 1),
        }

        return RiskReport(
            tick=world.tick,
            ts=world.ts,
            score=round(score, 1),
            level=level,
            clarity=round(clarity, 1),
            drivers=drivers,
            notes="synthetic risk blend",
        )


class DefaultPolicyModule:
    def run(self, world: WorldState, risk: RiskReport) -> List[Intent]:
        intents: List[Intent] = []

        # Always maintain base "continue" intent
        intents.append(
            Intent(
                id=str(uuid.uuid4()),
                kind="CONTINUE",
                priority=10,
                rationale="Baseline keep-going behavior",
            )
        )

        if risk.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            intents.append(
                Intent(
                    id=str(uuid.uuid4()),
                    kind="SLOW_ROLL",
                    priority=50,
                    params={"rate_multiplier": 0.5},
                    rationale=f"Risk {risk.score} ≥ HIGH; slow systems",
                )
            )

        if risk.level is RiskLevel.CRITICAL:
            intents.append(
                Intent(
                    id=str(uuid.uuid4()),
                    kind="EMERGENCY",
                    priority=90,
                    params={"mode": "HOLD"},
                    rationale="Critical risk; hold until operator review",
                )
            )

        # Sort by priority descending
        intents.sort(key=lambda i: i.priority, reverse=True)
        return intents


class DefaultProposalModule:
    def run(self,
            intents: List[Intent],
            world: WorldState,
            risk: RiskReport) -> List[Proposal]:
        proposals: List[Proposal] = []
        for intent in intents:
            if intent.kind == "CONTINUE":
                action = "Maintain current profile"
                bounds = {"max_delta": "minimal"}
            elif intent.kind == "SLOW_ROLL":
                action = "Reduce operational rate"
                bounds = {"rate_multiplier": intent.params.get("rate_multiplier", 0.6)}
            elif intent.kind == "EMERGENCY":
                action = "Enter safe hold"
                bounds = {"hold": True}
            else:
                action = f"Custom intent {intent.kind}"
                bounds = {}

            proposals.append(
                Proposal(
                    id=str(uuid.uuid4()),
                    tick=world.tick,
                    source_intent=intent.kind,
                    action=action,
                    bounds=bounds,
                    expected_effect={
                        "risk_delta": -10,  # just a placeholder
                        "clarity_delta": +5,
                    },
                )
            )
        return proposals


class DefaultGovernanceModule:
    def run(self,
            proposals: List[Proposal],
            world: WorldState,
            risk: RiskReport,
            config: GovernanceConfig) -> List[Decision]:
        decisions: List[Decision] = []

        for p in proposals:
            status = ProposalStatus.PENDING
            comment = ""

            if risk.score >= config.hard_block_risk:
                status = ProposalStatus.BLOCKED
                comment = f"Blocked: risk {risk.score} ≥ hard stop"
            elif not config.gate_open:
                status = ProposalStatus.REQUIRES_HUMAN
                comment = "Gate closed; human review required"
            elif risk.score > config.max_auto_risk or \
                    p.source_intent in config.require_human_for:
                status = ProposalStatus.REQUIRES_HUMAN
                comment = f"Risk {risk.score} or intent {p.source_intent} above auto threshold"
            else:
                status = ProposalStatus.AUTO_APPROVED
                comment = "Within auto-go envelope"

            p.status = status
            p.governance_notes = comment

            decisions.append(
                Decision(
                    id=str(uuid.uuid4()),
                    proposal_id=p.id,
                    tick=p.tick,
                    status=status,
                    operator="AUTO" if status == ProposalStatus.AUTO_APPROVED else "HUMAN?",
                    comment=comment,
                )
            )
        return decisions


class DefaultActuationModule:
    def run(self, decisions: List[Decision],
            world: WorldState) -> List[ActuationCommand]:
        cmds: List[ActuationCommand] = []
        for d in decisions:
            if d.status == ProposalStatus.AUTO_APPROVED:
                cmds.append(
                    ActuationCommand(
                        id=str(uuid.uuid4()),
                        tick=d.tick,
                        channel="core",
                        payload={
                            "decision_id": d.id,
                            "proposal_id": d.proposal_id,
                            "mode": "EXECUTE",
                        },
                    )
                )
        return cmds


# =========================
# 5. Kernel
# =========================

class AutonomyKernel:
    def __init__(
        self,
        sensor: SensorAdapter,
        perception: PerceptionModule,
        risk: RiskModule,
        policy: PolicyModule,
        proposals: ProposalModule,
        governance: GovernanceModule,
        actuation: ActuationModule,
        governance_config: Optional[GovernanceConfig] = None,
    ) -> None:
        self.sensor = sensor
        self.perception = perception
        self.risk_module = risk
        self.policy_module = policy
        self.proposal_module = proposals
        self.governance_module = governance
        self.actuation_module = actuation
        self.gov_cfg = governance_config or GovernanceConfig()

        self.tick_id: TickId = 0
        self.prev_world: Optional[WorldState] = None
        self.audit_chain: List[AuditEntry] = []
        self.prev_hash: str = "0" * 64

    # ---- internal ----

    def _audit(self, kind: str, payload: Dict[str, Any]) -> AuditEntry:
        entry_id = str(uuid.uuid4())
        ts = time.time()
        raw = {
            "id": entry_id,
            "tick": self.tick_id,
            "ts": ts,
            "kind": kind,
            "payload": payload,
            "prev_hash": self.prev_hash,
        }
        h = sha256(raw)
        entry = AuditEntry(
            id=entry_id,
            tick=self.tick_id,
            ts=ts,
            kind=kind,
            payload=payload,
            prev_hash=self.prev_hash,
            hash=h,
        )
        self.prev_hash = h
        self.audit_chain.append(entry)
        return entry

    # ---- public ----

    def step(self) -> TickResult:
        """Run one full kernel tick."""
        self.tick_id += 1

        frame = self.sensor.read(self.tick_id, self.prev_world)
        world = self.perception.run(frame, self.prev_world)
        risk = self.risk_module.run(world)
        intents = self.policy_module.run(world, risk)
        proposals = self.proposal_module.run(intents, world, risk)
        decisions = self.governance_module.run(proposals, world, risk, self.gov_cfg)
        actuation = self.actuation_module.run(decisions, world)

        # Audit everything at a coarse level
        audit_entries = [
            self._audit("frame", {"streams": frame.streams}),
            self._audit("risk", {"score": risk.score, "level": risk.level.name}),
            self._audit("intents", {"count": len(intents)}),
            self._audit("proposals", {"count": len(proposals)}),
            self._audit("decisions", {"count": len(decisions)}),
            self._audit("actuation", {"count": len(actuation)}),
        ]

        self.prev_world = world

        return TickResult(
            tick=self.tick_id,
            sensor_frame=frame,
            world=world,
            risk=risk,
            intents=intents,
            proposals=proposals,
            decisions=decisions,
            actuation=actuation,
            audit_entries=audit_entries,
        )


# =========================
# 6. Minimal CLI harness
# =========================

def pretty_tick(tr: TickResult) -> str:
    return (
        f"tick {tr.tick:03d} | "
        f"risk {tr.risk.score:5.1f} ({tr.risk.level.name}) | "
        f"clarity {tr.risk.clarity:5.1f} | "
        f"intents {len(tr.intents):2d} | "
        f"props {len(tr.proposals):2d} | "
        f"auto_cmds {len(tr.actuation):2d}"
    )


if __name__ == "__main__":
    # Default wiring
    kernel = AutonomyKernel(
        sensor=SyntheticSensorAdapter(),
        perception=DefaultPerceptionModule(),
        risk=DefaultRiskModule(),
        policy=DefaultPolicyModule(),
        proposals=DefaultProposalModule(),
        governance=DefaultGovernanceModule(),
        actuation=DefaultActuationModule(),
        governance_config=GovernanceConfig(
            max_auto_risk=45.0,
            hard_block_risk=85.0,
            gate_open=True,  # flip to False to simulate human-gate lock
        ),
    )

    print("Agnostic Autonomy Kernel — demo loop (Ctrl+C to stop)")
    try:
        while True:
            tr = kernel.step()
            print(pretty_tick(tr))
            time.sleep(0.7)
    except KeyboardInterrupt:
        print("\nStopped.")
        print(f"Total ticks: {kernel.tick_id}")
        print(f"Audit length: {len(kernel.audit_chain)}")