CIVIC-OS Orchestrator (Executable Scaffold)
- Runs a CIVIC-OS cycle with:
  - AuditGate (Truth/Logic/Risk/Bias/Clarity)
  - FalsifierEngine (metric-based falsification)
  - SignedMemory (append-only signed log)

This orchestrator is tool-agnostic:
- You can plug in an LLM to generate artifacts for each stage,
  but it also works with provided artifacts.

Usage (minimal demo):
  from civic_os.orchestrator import CivicOSOrchestrator, RunInput
  orch = CivicOSOrchestrator()
  result = orch.run(RunInput(task="Reduce service latency..."))
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from civic_os.audit_gate import AuditGate, AuditContext
from civic_os.falsifier_engine import FalsifierEngine, MetricsSnapshot
from civic_os.signed_memory import SignedMemory, SignedEntry


@dataclass
class RunInput:
    task: str
    artifacts: Dict[str, Any] = field(default_factory=dict)  # optional prefilled artifacts
    metrics_current: Optional[Dict[str, Any]] = None         # optional observed metrics
    metrics_baseline: Optional[Dict[str, Any]] = None        # optional baseline
    window: str = "weekly"
    domain: str = "unknown"


@dataclass
class RunResult:
    run_id: str
    audit_overall: str                 # PASS/FAIL
    falsifier_verdict: str             # OK/FALSIFIED (or OK with baseline_missing warnings)
    outputs: Dict[str, Any]            # audit report + falsifier result + artifacts
    run_dir: str


class CivicOSOrchestrator:
    CODEX_ID = "CIVIC-OS-TH v1.0"

    def __init__(
        self,
        run_root: str = "runs",
        strict_audit: bool = True,
        require_baseline_for_falsifiers: bool = True,
    ):
        self.run_root = Path(run_root)
        self.run_root.mkdir(parents=True, exist_ok=True)

        self.audit_gate = AuditGate(strict=strict_audit)
        self.falsifier_engine = FalsifierEngine(require_baseline=require_baseline_for_falsifiers)

    # -------------------------
    # Main run
    # -------------------------
    def run(self, inp: RunInput) -> RunResult:
        run_id = self._new_run_id()
        run_dir = self.run_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        mem = SignedMemory(run_dir=str(run_dir))

        # Stage 0: seed minimal IC if missing
        artifacts = dict(inp.artifacts or {})
        artifacts = self._ensure_minimum_artifacts(task=inp.task, artifacts=artifacts)

        # Log run start
        mem.append(
            SignedEntry(
                run_id=run_id,
                seq=0,
                event="RUN_START",
                payload={
                    "codex_id": self.CODEX_ID,
                    "task": inp.task,
                    "domain": inp.domain,
                    "window": inp.window,
                    "strict_audit": self.audit_gate.strict,
                    "require_baseline_for_falsifiers": self.falsifier_engine.require_baseline,
                },
            )
        )

        # Stage 7: Audit Gate
        audit_ctx = AuditContext(artifacts=artifacts, metadata={"domain": inp.domain})
        audit_report = self.audit_gate.evaluate(audit_ctx).to_dict()

        mem.append(
            SignedEntry(
                run_id=run_id,
                seq=0,
                event="AUDIT_REPORT",
                payload=audit_report,
            )
        )

        # Falsifier evaluation (optional)
        falsifier_result = None
        falsifier_verdict = "OK"
        if inp.metrics_current is not None:
            snap = MetricsSnapshot(
                current=inp.metrics_current,
                baseline=inp.metrics_baseline,
                window=inp.window,
                metadata={"domain": inp.domain},
            )
            falsifier_result = self.falsifier_engine.evaluate(snap).to_dict()
            falsifier_verdict = falsifier_result["verdict"]

            mem.append(
                SignedEntry(
                    run_id=run_id,
                    seq=0,
                    event="FALSIFIER_RESULT",
                    payload=falsifier_result,
                )
            )

        # Decide final run status
        audit_overall = audit_report["overall_verdict"]
        final_status = "PASS"
        if audit_overall == "FAIL":
            final_status = "BLOCKED_BY_AUDIT"
        elif falsifier_verdict == "FALSIFIED":
            final_status = "FALSIFIED_IN_MONITORING"

        mem.append(
            SignedEntry(
                run_id=run_id,
                seq=0,
                event="RUN_END",
                payload={
                    "final_status": final_status,
                    "audit_overall": audit_overall,
                    "falsifier_verdict": falsifier_verdict,
                    "notes": "Staged rollout only. If audit FAIL or falsified => freeze/rollback + model upgrade.",
                },
            )
        )

        outputs = {
            "artifacts": artifacts,
            "audit_report": audit_report,
            "falsifier_result": falsifier_result,
            "final_status": final_status,
            "signed_log_path": str(run_dir / "signed_log.jsonl"),
        }

        return RunResult(
            run_id=run_id,
            audit_overall=audit_overall,
            falsifier_verdict=falsifier_verdict,
            outputs=outputs,
            run_dir=str(run_dir),
        )

    # -------------------------
    # Helpers
    # -------------------------
    def _new_run_id(self) -> str:
        # short but unique enough for local runs
        return f"{uuid.uuid4().hex[:12]}"

    def _ensure_minimum_artifacts(self, task: str, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensures the minimum artifacts exist so AuditGate can operate.
        You can replace this with LLM-generated stages later.
        """
        # IC
        if "IC" not in artifacts:
            artifacts["IC"] = {
                "Goal": task,
                "Deliverable": "A staged reform/service redesign plan with measurable outcomes",
                "Constraints": ["Legality", "Due process", "Auditability", "Rollback-by-default"],
                "Success metrics": [
                    "service_latency_median",
                    "service_latency_p90",
                    "error_rate",
                    "transparency_coverage",
                    "citizen_burden_index",
                    "disparity_index",
                ],
                "Citizen summary": (
                    "This change aims to reduce time and burden for citizens while keeping decisions fair and traceable. "
                    "We will roll out in stages (pilot → limited rollout → scale) and publish outcome metrics. "
                    "If errors, appeals, or inequality worsen, we pause and roll back."
                ),
            }

        # ES
        if "ES" not in artifacts:
            artifacts["ES"] = {
                "Facts": ["Baseline metrics exist or will be collected in pilot."],
                "Assumptions": ["Digitization reduces burden if steps are removed, not replicated."],
                "Unknowns": ["Frontline workload shift risk", "Disparity changes by region"],
                "Sources": [],
                "Data risks": ["Sampling bias", "Gaming KPIs"],
            }

        # FPF
        if "FPF" not in artifacts:
            artifacts["FPF"] = {
                "Axioms": [
                    "Incentives shape behavior more than slogans.",
                    "What is not measured becomes theatre.",
                ],
                "Invariants": ["Time/attention finite", "Trust fragile"],
                "Variables": ["queue_size", "review_capacity", "validation_rules", "appeal_load"],
                "Levers": ["staged_rollout", "midpoint_validation", "simplify_steps", "trace_logging"],
                "Falsifiers": [
                    "Latency down but errors/appeals up",
                    "Throughput up but disparity up",
                    "Citizen burden increases after 'digital'",
                ],
                "Minimal tests": [
                    "Pilot in 1-2 districts, measure p90 latency + error_rate",
                    "A/B test simplified steps vs existing",
                    "Equity monitoring by region/group",
                ],
            }

        # WM
        if "WM" not in artifacts:
            artifacts["WM"] = {
                "Causal structure": "Queue + capacity + validation quality determine latency and error rate.",
                "Loops": ["Rework loop: errors increase rework which increases latency"],
                "Delays": ["Policy changes reflect in metrics with 2-4 week lag"],
                "Bottlenecks": ["Review step"],
                "Constraints": ["Legal due process", "Staff capacity"],
            }

        # SM
        if "SM" not in artifacts:
            artifacts["SM"] = {
                "Boundary": "Service delivery workflow and approvals",
                "Actors & incentives": [
                    "Citizens: want fast + fair",
                    "Frontline staff: workload + risk avoidance",
                    "Managers: KPI + reputation",
                ],
                "Hidden costs/externalities": ["Shadow paperwork", "Increased appeals load"],
                "Feedback loops/delays": ["Errors → appeals → delays → public trust drop"],
                "Corruption surfaces": ["Discretion points without logs"],
                "Capacity constraints": ["Review staff count", "IT throughput"],
            }

        # DS (3 options)
        if "DS" not in artifacts:
            artifacts["DS"] = {
                "Option A": {
                    "name": "Safe",
                    "description": "Pilot only with strict validation and manual oversight.",
                    "Downside": "Slower improvement",
                    "Triggers/Kill-switch": "If error_rate +10% or disparity +5% => pause/rollback",
                },
                "Option B": {
                    "name": "Balanced",
                    "description": "Pilot + limited rollout with automated checks and public dashboards.",
                    "Downside": "Moderate risk",
                    "Triggers/Kill-switch": "If p90 latency not improved within 4 weeks => revise levers",
                },
                "Option C": {
                    "name": "Aggressive",
                    "description": "Fast scale with automation; only if audit gates pass strongly.",
                    "Downside": "High risk of hidden failures",
                    "Triggers/Kill-switch": "Any audit FAIL or falsifier HIGH => freeze immediately",
                },
                "Global downside bound": "No scaling if any HIGH falsifier triggers; rollback to last stable stage.",
                "Rollback plan": "Revert to prior workflow + keep logs; rerun pilot with revised constraints.",
                "Kill-switch": "Immediate freeze of rollout; route new cases to safe path.",
            }

        # AP
        if "AP" not in artifacts:
            artifacts["AP"] = {
                "Stages": ["Pilot", "Limited rollout", "Scale"],
                "Instrumentation": "Collect latency/error/appeal/burden/disparity + trace logs per step.",
                "Metrics & thresholds": {
                    "error_rate": "must not increase >10%",
                    "disparity_index": "must not increase >5%",
                    "transparency_coverage": "must be >= 0.60",
                },
                "Rollback": "If thresholds breached, revert to previous stage and publish incident note.",
                "Kill-switch": "Freeze scaling; revert routing to pilot-safe workflow.",
                "Execution checklist": [
                    "Define baseline metrics (median/p90 latency, error_rate, burden, disparity)",
                    "Enable trace logging for all decision points",
                    "Run weekly audit review meeting (Verifier can veto)",
                ],
                "Citizen summary": (
                    "We are improving the service in stages. We will publish metrics and keep decisions traceable. "
                    "If quality, fairness, or burden worsens, we stop and roll back."
                ),
            }

        return artifacts
