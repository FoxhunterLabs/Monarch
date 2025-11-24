Agnostic Autonomy Kernel v0.1
A deterministic-ish, domain-agnostic autonomy core designed around tick-based state
progression, strict human-gating, and pluggable modules for perception, risk, policy, proposals,
governance, and actuation.
This is a kernel, not a product:
It gives you the skeleton of an autonomy loop without baking in robotics, vehicles, drones, or
industrial systems. Anything can plug in at the edges.
Drop it into Replit as app.py, press Run, and it lives.
What It Is
A minimal autonomy core built to be:
• Systems-agnostic — no physics, no domain assumptions.
• Deterministic-ish — runs on discrete ticks with stable module ordering.
• Human-gated — governance layer enforces operator-in-the-loop logic.
• Fully pluggable — every stage is driven by a Protocol interface.
• Auditable — each tick appends to a tamper-evident hash chain.
Ideal for prototyping autonomy, safety envelopes, and governance logic without committing to
an ecosystem.
Core Flow (1 Tick)
Every tick runs the full six-layer autonomy chain:
1. SensorAdapter → generate raw SensorFrame
2. PerceptionModule → convert to semantic WorldState
3. RiskModule → produce RiskReport
4. PolicyModule → emit prioritized Intents
5. ProposalModule → translate to Proposals
6. GovernanceModule → gate / approve / block
7. ActuationModule → produce ActuationCommands
8. Audit → append hash-linked entry
All results are packaged into a TickResult struct for UIs, logging, or downstream systems.
Architecture Overview
1. Data Models
Strongly typed dataclasses for:
• SensorFrame – raw channels per tick
• WorldState – semantic facts + subsystem health
• RiskReport – 0–100 score, clarity, drivers
• Intent – high-level behavior w/ priorities
• Proposal – concrete system actions
• Decision – governance output
• ActuationCommand – final actuator payload
• AuditEntry – hashed chain for tamper detection
Everything is timestamped, tick-indexed, and machine-parseable.
2. Module Interfaces
Each part of the autonomy stack is defined via a Python Protocol:
class PerceptionModule(Protocol):
def run(self, frame: SensorFrame, prev_world: Optional[WorldState]) ->
WorldState: ...
This keeps the kernel stable while allowing you to hot-swap behaviors, physics models, risk
engines, governance policies, etc.
3. Default Implementations
The kernel ships with deterministic-ish synthetic modules so the loop runs out of the box:
• Synthetic sensor adapter
• Simple perception model
• Weighted risk calculator
• Intent generator (CONTINUE, SLOW_ROLL, EMERGENCY)
• Proposal builder
• Governance engine with auto/human/blocked logic
• Actuation stub that emits commands from auto-approved decisions
These make the demo self-contained and show clean examples of module structure.
4. Governance & Safety
Human gating is first-class.
The GovernanceConfig controls:
• max_auto_risk — auto-approve ceiling
• hard_block_risk — absolute safety cutoff
• require_human_for — intents that always require a human
• gate_open — master human-approval switch
The governance module strictly enforces these rules before any actuation occurs.
Running the Demo
Replit or local:
python app.py
You’ll see output like:
tick 001 | risk 32.4 (ELEVATED) | clarity 81.0 | intents 02 | props 02 |
auto_cmds 01
auto_cmds 01
...
tick 002 | risk 44.7 (ELEVATED) | clarity 73.2 | intents 02 | props 02 |
Press Ctrl+C to exit.
It prints total ticks and audit chain length.
Plugging In Your Own Modules
Swap any module by passing your own implementation into the kernel constructor:
kernel = AutonomyKernel(
sensor=MySensorAdapter(),
perception=MyPerception(),
risk=MyRiskEngine(),
policy=MyPolicy(),
proposals=MyProposalGenerator(),
governance=MyGovernanceLogic(),
actuation=MyActuator(),
)
Everything else stays the same.
Why This Matters
This kernel is built for:
• Deterministic autonomy research
• Infrastructure autonomy
• Safety-envelope design
• Human-in-the-loop systems
• Rapid prototyping for robotics, industrial processes, vehicles, or distributed systems
• Teaching & explaining autonomy loops without domain complexity
It’s intentionally small, auditable, and composable.
License
MIT