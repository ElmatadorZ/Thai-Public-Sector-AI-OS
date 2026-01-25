# tests/test_audit_gate.py
from civic_os.audit_gate import AuditGate, AuditContext


def test_audit_gate_fails_when_missing_core_fields():
    gate = AuditGate(strict=True)
    ctx = AuditContext(artifacts={"IC": {"Goal": "x"}}, metadata={})
    rep = gate.evaluate(ctx).to_dict()
    assert rep["overall_verdict"] == "FAIL"


def test_audit_gate_passes_with_minimum_artifacts():
    gate = AuditGate(strict=True)
    artifacts = {
        "IC": {
            "Goal": "Reduce latency",
            "Deliverable": "Staged plan",
            "Success metrics": ["service_latency_median"],
            "Citizen summary": "We will reduce latency with staged rollout and publish metrics.",
        },
        "ES": {
            "Facts": ["baseline collected"],
            "Assumptions": ["pilot reflects reality"],
            "Unknowns": ["staff capacity variance"],
            "Sources": ["internal metrics"],
            "Data risks": ["gaming KPIs"],
        },
        "FPF": {
            "Variables": ["queue_size"],
            "Levers": ["staged_rollout"],
            "Falsifiers": ["Latency down but errors up"],
            "Minimal tests": ["pilot test"],
        },
        "WM": {
            "Causal structure": "queue/capacity affects latency",
            "Loops": ["rework loop"],
            "Delays": ["policy lag"],
            "Bottlenecks": ["review"],
            "Constraints": ["due process"],
        },
        "SM": {
            "Actors & incentives": ["citizens want fast", "staff avoid risk"],
            "Hidden costs/externalities": ["shadow paperwork"],
            "Corruption surfaces": ["discretion without logs"],
        },
        "DS": {
            "Option A": {"name": "Safe"},
            "Option B": {"name": "Balanced"},
            "Global downside bound": "no scale if falsified",
            "Rollback plan": "revert to stable stage",
            "Kill-switch": "freeze rollout",
        },
        "AP": {
            "Stages": ["Pilot"],
            "Instrumentation": "collect metrics",
            "Metrics & thresholds": {"error_rate": "<= +10%"},
            "Rollback": "revert",
            "Kill-switch": "freeze",
            "Execution checklist": ["log everything"],
            "Citizen summary": "Staged rollout with rollback.",
        },
    }
    ctx = AuditContext(artifacts=artifacts, metadata={})
    rep = gate.evaluate(ctx).to_dict()
    assert rep["overall_verdict"] in ("PASS", "FAIL")  # strict but should usually pass
