CIVIC-OS Falsifier Engine
Evaluates whether observed metrics falsify the current decision/model.

Key idea:
- Metrics are not "vanity dashboards"
- Falsifiers are observable conditions that invalidate a thesis
- When falsified => trigger rollback, audit FAIL, and model upgrade request

This engine supports:
- Built-in canonical falsifiers (from CIVIC-OS Codex)
- Custom falsifiers loaded from DSL/YAML later (hook provided)

Usage:
  from civic_os.falsifier_engine import FalsifierEngine, MetricsSnapshot
  engine = FalsifierEngine()
  result = engine.evaluate(snapshot)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MetricsSnapshot:
    """
    Current observed metrics. Use raw numbers as floats/ints where possible.

    Recommended keys:
      - service_latency_median
      - service_latency_p90
      - throughput
      - error_rate
      - transparency_coverage
      - appeal_resolution_time
      - citizen_burden_index
      - disparity_index
      - shadow_paperwork_index (optional proxy)
    """
    current: Dict[str, Any]
    baseline: Optional[Dict[str, Any]] = None  # pre-change baseline
    window: str = "unknown"  # e.g., "weekly", "monthly"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FalsifierHit:
    code: str
    title: str
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    evidence: Dict[str, Any]
    recommendation: str


@dataclass
class FalsifierResult:
    timestamp_utc: str
    verdict: str  # "OK" | "FALSIFIED"
    hits: List[FalsifierHit]
    summary: str
    recommended_actions: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "verdict": self.verdict,
            "summary": self.summary,
            "recommended_actions": self.recommended_actions,
            "hits": [
                {
                    "code": h.code,
                    "title": h.title,
                    "severity": h.severity,
                    "evidence": h.evidence,
                    "recommendation": h.recommendation,
                }
                for h in self.hits
            ],
            "metadata": self.metadata,
        }


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _pct_change(cur: Optional[float], base: Optional[float]) -> Optional[float]:
    if cur is None or base is None:
        return None
    if base == 0:
        return None
    return (cur - base) / abs(base)


class FalsifierEngine:
    """
    Default canonical falsifiers (codex):
      - latency_down_errors_up
      - throughput_up_disparity_up
      - transparency_claims_unverifiable_logs (approximated by transparency_coverage but missing audit logs)
      - shadow_paperwork_grows
      - citizen_burden_up_after_digital
    """

    def __init__(
        self,
        thresholds: Optional[Dict[str, float]] = None,
        require_baseline: bool = True,
    ):
        # Default thresholds tuned for public systems; adjust per domain.
        self.thresholds = {
            "latency_improve": -0.10,       # -10% median latency is "improve"
            "error_worsen": 0.10,           # +10% error rate is "worsen"
            "throughput_improve": 0.10,     # +10% throughput is "improve"
            "disparity_worsen": 0.05,       # +5% disparity index is "worsen"
            "transparency_min": 0.60,       # must be >= 0.60 to claim improved transparency
            "burden_worsen": 0.05,          # +5% citizen burden is "worsen"
            "shadow_paperwork_worsen": 0.10 # +10% shadow paperwork index is "worsen"
        }
        if thresholds:
            self.thresholds.update(thresholds)
        self.require_baseline = require_baseline

    def evaluate(self, snap: MetricsSnapshot) -> FalsifierResult:
        cur = snap.current or {}
        base = snap.baseline

        hits: List[FalsifierHit] = []
        actions: List[str] = []

        if self.require_baseline and not base:
            # Without baseline we can still do absolute checks for some metrics,
            # but we should not declare "FALSIFIED" unless clearly unsafe.
            hits.append(
                FalsifierHit(
                    code="baseline_missing",
                    title="Baseline missing (cannot compute falsifiers reliably)",
                    severity="MEDIUM",
                    evidence={"window": snap.window},
                    recommendation="Provide baseline metrics (pre-change) or mark this as exploratory pilot only.",
                )
            )
            actions.append("เติม baseline metrics ก่อนสรุปผล (หรือประกาศว่าเป็น pilot exploratory)")

        # Compute changes where possible
        def ch(key: str) -> Optional[float]:
            return _pct_change(_num(cur.get(key)), _num(base.get(key)) if base else None)

        # 1) latency_down_errors_up
        latency_change = ch("service_latency_median")
        error_change = ch("error_rate")
        if latency_change is not None and error_change is not None:
            if latency_change <= self.thresholds["latency_improve"] and error_change >= self.thresholds["error_worsen"]:
                hits.append(
                    FalsifierHit(
                        code="latency_down_errors_up",
                        title="Latency improved but error rate worsened (dashboard theatre risk)",
                        severity="HIGH",
                        evidence={
                            "service_latency_median_change": latency_change,
                            "error_rate_change": error_change,
                        },
                        recommendation="Trigger rollback or tighten validation gates; optimize correctness before speed.",
                    )
                )
                actions += [
                    "สั่งหยุดขยายผล (freeze rollout) และทำ rollback หากจำเป็น",
                    "เพิ่ม Audit/Validation ขั้นกลางก่อนจุดอนุมัติ (ลด error ก่อนลดเวลา)",
                ]

        # 2) throughput_up_disparity_up
        throughput_change = ch("throughput")
        disparity_change = ch("disparity_index")
        if throughput_change is not None and disparity_change is not None:
            if throughput_change >= self.thresholds["throughput_improve"] and disparity_change >= self.thresholds["disparity_worsen"]:
                hits.append(
                    FalsifierHit(
                        code="throughput_up_disparity_up",
                        title="Throughput improved but disparity widened (fairness regression)",
                        severity="HIGH",
                        evidence={
                            "throughput_change": throughput_change,
                            "disparity_index_change": disparity_change,
                        },
                        recommendation="Pause scaling; add equity constraints and re-run pilot with bias monitoring.",
                    )
                )
                actions += [
                    "หยุด scale และใส่ equity constraints (สิทธิ/การเข้าถึง) เป็นเงื่อนไขบังคับ",
                    "เพิ่ม monitoring แยกตามพื้นที่/กลุ่ม และตั้ง threshold disparity",
                ]

        # 3) transparency_claims_unverifiable_logs (approx)
        # We can't verify logs here without signed_memory integration.
        # Use a proxy: if transparency_coverage did not improve OR is below minimum,
        # treat transparency claims as suspect.
        trans_cur = _num(cur.get("transparency_coverage"))
        trans_base = _num(base.get("transparency_coverage")) if base else None
        trans_change = _pct_change(trans_cur, trans_base) if (trans_cur is not None and trans_base is not None) else None
        if trans_cur is not None:
            if trans_cur < self.thresholds["transparency_min"]:
                hits.append(
                    FalsifierHit(
                        code="transparency_claims_unverifiable_logs",
                        title="Transparency coverage below minimum (claims not supportable)",
                        severity="MEDIUM",
                        evidence={"transparency_coverage": trans_cur, "min_required": self.thresholds["transparency_min"]},
                        recommendation="Increase traceability/logging coverage before claiming transparency improvements.",
                    )
                )
                actions.append("เพิ่ม trace/log coverage ให้เกินเกณฑ์ขั้นต่ำก่อนประกาศความโปร่งใส")

        # 4) shadow_paperwork_grows
        shadow_change = ch("shadow_paperwork_index")
        if shadow_change is not None and shadow_change >= self.thresholds["shadow_paperwork_worsen"]:
            hits.append(
                FalsifierHit(
                    code="shadow_paperwork_grows",
                    title="Shadow paperwork increased (work shifted outside the system)",
                    severity="HIGH",
                    evidence={"shadow_paperwork_index_change": shadow_change},
                    recommendation="Stop rollout; redesign workflow to eliminate off-system steps; audit incentives.",
                )
            )
            actions += [
                "หยุด rollout และ map ขั้นตอนเงา (shadow steps) ออกมาให้ครบ",
                "ปรับ incentive/KPI ให้รางวัลกับ outcome ไม่ใช่การหลบระบบ",
            ]

        # 5) citizen_burden_up_after_digital
        burden_change = ch("citizen_burden_index")
        if burden_change is not None and burden_change >= self.thresholds["burden_worsen"]:
            hits.append(
                FalsifierHit(
                    code="citizen_burden_up_after_digital",
                    title="Citizen burden increased after digitization (UX regression)",
                    severity="HIGH",
                    evidence={"citizen_burden_index_change": burden_change},
                    recommendation="Rollback UX/process; reduce steps/docs/trips; validate with citizen journey tests.",
                )
            )
            actions += [
                "ทำ citizen journey test ใหม่ และลด steps/docs/trips ให้ชัด",
                "ตั้ง policy: digitization must reduce burden (ไม่งั้นถือว่าล้มเหลว)",
            ]

        # Optional absolute safety checks (even without baseline)
        # If error_rate is extremely high or transparency extremely low, flag.
        err_cur = _num(cur.get("error_rate"))
        if err_cur is not None and err_cur >= 0.20:
            hits.append(
                FalsifierHit(
                    code="error_rate_extreme",
                    title="Error rate extremely high (unsafe to scale)",
                    severity="HIGH",
                    evidence={"error_rate": err_cur},
                    recommendation="Do not scale. Add validation, training, and staged gates immediately.",
                )
            )
            actions.append("ห้าม scale; เพิ่ม validation/training และทำ staged rollout")

        # Decide verdict
        high_hits = [h for h in hits if h.severity == "HIGH"]
        verdict = "FALSIFIED" if len(high_hits) > 0 else "OK"

        if verdict == "FALSIFIED":
            summary = f"FALSIFIED — {len(high_hits)} high-severity falsifiers triggered. Rollout should be paused/rolled back."
        else:
            summary = f"OK — No high-severity falsifiers triggered. Continue staged monitoring."

        # De-dup actions
        dedup_actions: List[str] = []
        for a in actions:
            if a not in dedup_actions:
                dedup_actions.append(a)

        return FalsifierResult(
            timestamp_utc=_now_utc_iso(),
            verdict=verdict,
            hits=hits,
            summary=summary,
            recommended_actions=dedup_actions[:10],
            metadata={
                "window": snap.window,
                "require_baseline": self.require_baseline,
                "thresholds": self.thresholds,
                **(snap.metadata or {}),
            },
        )
