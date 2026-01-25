CIVIC-OS Audit Gate
Truth • Logic • Risk • Bias • Clarity  => PASS/FAIL

Design goals:
- Persona-independent, evidence-first
- Deterministic where possible
- Strict defaults: if missing critical fields => FAIL
- Produces actionable fixes (minimum viable fixes)

Usage:
  from civic_os.audit_gate import AuditGate, AuditContext
  gate = AuditGate()
  report = gate.evaluate(ctx)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


Verdict = str  # "PASS" or "FAIL"


# -----------------------------
# Data models
# -----------------------------
@dataclass
class GateResult:
    gate: str
    verdict: Verdict
    notes: List[str] = field(default_factory=list)
    fixes: List[str] = field(default_factory=list)
    score: float = 0.0  # 0..1 heuristic

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate,
            "verdict": self.verdict,
            "score": round(self.score, 3),
            "notes": self.notes,
            "fixes": self.fixes,
        }


@dataclass
class AuditReport:
    codex_id: str
    timestamp_utc: str
    overall_verdict: Verdict
    gate_results: List[GateResult]
    summary: str
    minimum_fixes: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "codex_id": self.codex_id,
            "timestamp_utc": self.timestamp_utc,
            "overall_verdict": self.overall_verdict,
            "summary": self.summary,
            "minimum_fixes": self.minimum_fixes,
            "gate_results": [gr.to_dict() for gr in self.gate_results],
            "metadata": self.metadata,
        }


@dataclass
class AuditContext:
    """
    A minimal, tool-agnostic context for auditing a decision/process change.

    Expected artifacts (dict-like) keys:
      - IC, SM, FPF, ES, WM, DS, AP, AR (optional, will be generated), SL (optional), MU (optional)

    You can pass additional metadata such as:
      - domain: "service_latency" | "procurement" | ...
      - stage: current stage identifier
    """
    artifacts: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


# -----------------------------
# Helpers
# -----------------------------
def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_nonempty_str(x: Any) -> bool:
    return isinstance(x, str) and x.strip() != ""


def _as_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _get(d: Dict[str, Any], *path: str, default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _has_any_textual_evidence(es: Dict[str, Any]) -> bool:
    facts = _as_list(es.get("Facts") or es.get("facts"))
    # Allow either explicit sources or at least fact statements
    if len([f for f in facts if _is_nonempty_str(f) or isinstance(f, dict)]) > 0:
        return True
    sources = _as_list(es.get("Sources") or es.get("sources"))
    if len([s for s in sources if _is_nonempty_str(s) or isinstance(s, dict)]) > 0:
        return True
    return False


def _count_missing_required(required: List[Tuple[str, Any]]) -> List[str]:
    missing = []
    for name, val in required:
        if val is None:
            missing.append(name)
        elif isinstance(val, str) and val.strip() == "":
            missing.append(name)
        elif isinstance(val, list) and len(val) == 0:
            missing.append(name)
        elif isinstance(val, dict) and len(val) == 0:
            missing.append(name)
    return missing


# -----------------------------
# Audit Gate
# -----------------------------
class AuditGate:
    CODEX_ID = "CIVIC-OS-TH v1.0"

    def __init__(self, strict: bool = True):
        """
        strict=True means missing critical fields => FAIL.
        """
        self.strict = strict

    def evaluate(self, ctx: AuditContext) -> AuditReport:
        artifacts = ctx.artifacts or {}
        metadata = ctx.metadata or {}

        truth = self._truth_gate(artifacts)
        logic = self._logic_gate(artifacts)
        risk = self._risk_gate(artifacts)
        bias = self._bias_gate(artifacts)
        clarity = self._clarity_gate(artifacts)

        gate_results = [truth, logic, risk, bias, clarity]
        overall = "PASS" if all(gr.verdict == "PASS" for gr in gate_results) else "FAIL"

        # Minimum fixes: take first fixes from failed gates (de-dup)
        fixes: List[str] = []
        for gr in gate_results:
            if gr.verdict == "FAIL":
                for f in gr.fixes:
                    if f not in fixes:
                        fixes.append(f)

        summary = self._summary(overall, gate_results)

        return AuditReport(
            codex_id=self.CODEX_ID,
            timestamp_utc=_now_utc_iso(),
            overall_verdict=overall,
            gate_results=gate_results,
            summary=summary,
            minimum_fixes=fixes[:8],  # keep concise
            metadata={
                "strict": self.strict,
                **metadata,
            },
        )

    # -------------------------
    # Gate 1: Truth
    # -------------------------
    def _truth_gate(self, artifacts: Dict[str, Any]) -> GateResult:
        es = artifacts.get("ES") or {}
        fpf = artifacts.get("FPF") or {}
        ds = artifacts.get("DS") or {}

        notes: List[str] = []
        fixes: List[str] = []

        facts = _as_list(es.get("Facts") or es.get("facts"))
        assumptions = _as_list(es.get("Assumptions") or es.get("assumptions"))
        unknowns = _as_list(es.get("Unknowns") or es.get("unknowns"))
        data_risks = _as_list(es.get("Data risks") or es.get("DataRisks") or es.get("data_risks"))

        falsifiers = _as_list(fpf.get("Falsifiers") or fpf.get("falsifiers"))
        minimal_tests = _as_list(fpf.get("Minimal tests") or fpf.get("MinimalTests") or fpf.get("minimal_tests"))

        # Required
        required = [
            ("ES.Facts", facts),
            ("ES.Assumptions", assumptions),
            ("FPF.Falsifiers", falsifiers),
        ]
        missing = _count_missing_required(required)

        if missing:
            notes.append(f"Missing required fields: {', '.join(missing)}")
            fixes.append("เติม ES: แยก Facts/Assumptions ให้ชัด และใส่ FPF.Falsifiers อย่างน้อย 3 ข้อ")

        # Evidence presence heuristic
        if not _has_any_textual_evidence(es):
            notes.append("Evidence looks weak: no sources or fact statements detected.")
            fixes.append("เพิ่มหลักฐาน: ใส่ Facts ที่ตรวจสอบได้ + Sources (ลิงก์/เอกสาร/ข้อมูลตัวอย่าง)")

        # Claims sanity: if DS has options but ES empty => likely narrative
        if (ds.get("Option A") or ds.get("OptionA") or ds.get("options")) and len(facts) == 0:
            notes.append("Decisions exist but no facts listed — risk of narrative-driven decision.")
            fixes.append("ก่อนตัดสินใจ: ใส่ Facts อย่างน้อย 5 ข้อ + ระบุ Unknowns ที่สำคัญ")

        # Testability
        if falsifiers and len(minimal_tests) == 0:
            notes.append("Falsifiers exist but minimal tests not specified.")
            fixes.append("เพิ่ม Minimal tests อย่างน้อย 3 ข้อเพื่อผูก Falsifiers กับการวัดผลจริง")

        score = self._score_from(missing=len(missing), penalties=0.2 if not _has_any_textual_evidence(es) else 0.0)
        verdict = "PASS" if len(missing) == 0 and _has_any_textual_evidence(es) else "FAIL"

        return GateResult("Truth Gate", verdict, notes, fixes, score)

    # -------------------------
    # Gate 2: Logic
    # -------------------------
    def _logic_gate(self, artifacts: Dict[str, Any]) -> GateResult:
        wm = artifacts.get("WM") or {}
        ds = artifacts.get("DS") or {}
        fpf = artifacts.get("FPF") or {}

        notes: List[str] = []
        fixes: List[str] = []

        causal = wm.get("Causal structure") or wm.get("causal_structure") or wm.get("CausalStructure")
        loops = _as_list(wm.get("Loops") or wm.get("loops"))
        delays = _as_list(wm.get("Delays") or wm.get("delays"))
        bottlenecks = _as_list(wm.get("Bottlenecks") or wm.get("bottlenecks"))

        # For decisions: require at least two options OR explicit rationale for single option
        optA = ds.get("Option A") or ds.get("OptionA")
        optB = ds.get("Option B") or ds.get("OptionB")
        optC = ds.get("Option C") or ds.get("OptionC")
        options_list = ds.get("options")
        options_count = 0
        options_count += 1 if optA else 0
        options_count += 1 if optB else 0
        options_count += 1 if optC else 0
        if isinstance(options_list, list):
            options_count = max(options_count, len(options_list))

        levers = _as_list(fpf.get("Levers") or fpf.get("levers"))
        variables = _as_list(fpf.get("Variables") or fpf.get("variables"))

        required = [
            ("WM.Causal structure", causal),
            ("FPF.Variables", variables),
            ("FPF.Levers", levers),
        ]
        missing = _count_missing_required(required)

        if missing:
            notes.append(f"Missing required fields: {', '.join(missing)}")
            fixes.append("เติม WM.Causal structure + FPF.Variables/Levers เพื่อให้เหตุผลครบวงจร")

        if options_count < 2:
            notes.append("Decision set has fewer than 2 options — weak counterfactual reasoning.")
            fixes.append("สร้างอย่างน้อย 2 ทางเลือก (Safe/Balanced/Aggressive) หรือระบุเหตุผลว่าทำไมมีทางเดียว")

        # Minimal systemic sanity: at least one bottleneck or loop or delay
        if len(loops) == 0 and len(delays) == 0 and len(bottlenecks) == 0:
            notes.append("World model lacks loops/delays/bottlenecks — risk of linear reasoning.")
            fixes.append("เพิ่ม Loops/Delays/Bottlenecks อย่างน้อยอย่างละ 1 (หรืออธิบายว่าทำไมไม่มี)")

        score = self._score_from(missing=len(missing), penalties=0.15 if options_count < 2 else 0.0)
        verdict = "PASS" if len(missing) == 0 and options_count >= 2 else "FAIL"

        return GateResult("Logic Gate", verdict, notes, fixes, score)

    # -------------------------
    # Gate 3: Risk
    # -------------------------
    def _risk_gate(self, artifacts: Dict[str, Any]) -> GateResult:
        ds = artifacts.get("DS") or {}
        ap = artifacts.get("AP") or {}

        notes: List[str] = []
        fixes: List[str] = []

        downside = ds.get("Global downside bound") or ds.get("GlobalDownsideBound") or ds.get("DownsideBound")
        rollback = ds.get("Rollback plan") or ds.get("Rollback") or ap.get("Rollback") or ap.get("rollback")
        kill_switch = ds.get("Kill-switch") or ds.get("KillSwitch") or ap.get("Kill-switch") or ap.get("KillSwitch")

        stages = _as_list(ap.get("Stages") or ap.get("stages") or ap.get("Steps") or ap.get("steps"))
        thresholds = ap.get("Thresholds") or ap.get("thresholds") or ap.get("Metrics & thresholds") or ap.get("metrics_thresholds")
        instrumentation = ap.get("Instrumentation") or ap.get("instrumentation")

        required = [
            ("DS.Global downside bound", downside),
            ("AP.Rollback", rollback),
            ("AP.Kill-switch", kill_switch),
        ]
        missing = _count_missing_required(required)

        if missing:
            notes.append(f"Missing required fields: {', '.join(missing)}")
            fixes.append("กำหนด Downside bound + Rollback + Kill-switch ให้ชัด (ห้าม deploy ถ้าไม่มี)")

        # Require staged execution for public systems
        if len(stages) == 0:
            notes.append("Action plan has no stages — public rollouts should be staged by default.")
            fixes.append("เพิ่ม Stages (Pilot → Limited rollout → Scale) พร้อมเกณฑ์ผ่านแต่ละด่าน")

        if not thresholds or not instrumentation:
            notes.append("Missing instrumentation/thresholds — cannot detect failure early.")
            fixes.append("เพิ่ม Instrumentation + Metrics/Thresholds เพื่อให้ kill-switch ทำงานได้จริง")

        score = self._score_from(missing=len(missing), penalties=0.15 if len(stages) == 0 else 0.0)
        verdict = "PASS" if len(missing) == 0 and len(stages) > 0 else "FAIL"

        return GateResult("Risk Gate", verdict, notes, fixes, score)

    # -------------------------
    # Gate 4: Bias
    # -------------------------
    def _bias_gate(self, artifacts: Dict[str, Any]) -> GateResult:
        sm = artifacts.get("SM") or {}
        es = artifacts.get("ES") or {}
        ds = artifacts.get("DS") or {}

        notes: List[str] = []
        fixes: List[str] = []

        actors = _as_list(sm.get("Actors & incentives") or sm.get("Actors") or sm.get("actors"))
        incentives = _as_list(sm.get("Incentives") or sm.get("incentives"))
        corruption = _as_list(sm.get("Corruption surfaces") or sm.get("corruption_surfaces"))
        hidden_costs = _as_list(sm.get("Hidden costs/externalities") or sm.get("hidden_costs"))

        # Bias checks: require at least one incentive statement and one risk surface
        required = [
            ("SM.Actors/Incentives", actors if actors else incentives),
            ("SM.Corruption surfaces", corruption),
            ("SM.Hidden costs/externalities", hidden_costs),
        ]
        missing = _count_missing_required(required)

        if missing:
            notes.append(f"Missing required fields: {', '.join(missing)}")
            fixes.append("เติม System Map: Actors/Incentives + Hidden costs + Corruption surfaces เพื่อกัน bias เชิงอำนาจ")

        # Narrative drift heuristic: if ES facts thin but DS confident language
        facts = _as_list(es.get("Facts") or es.get("facts"))
        if len(facts) < 3 and (ds.get("Option A") or ds.get("OptionA") or ds.get("options")):
            notes.append("Low fact count with active decisions — potential confirmation bias.")
            fixes.append("เพิ่ม Facts/Unknowns และใส่ counterarguments อย่างน้อย 2 ข้อใน DS/WM")

        score = self._score_from(missing=len(missing), penalties=0.1 if len(facts) < 3 else 0.0)
        verdict = "PASS" if len(missing) == 0 else "FAIL"

        return GateResult("Bias Gate", verdict, notes, fixes, score)

    # -------------------------
    # Gate 5: Clarity
    # -------------------------
    def _clarity_gate(self, artifacts: Dict[str, Any]) -> GateResult:
        ic = artifacts.get("IC") or {}
        ap = artifacts.get("AP") or {}
        # allow citizen summary anywhere
        citizen_summary = (
            artifacts.get("CitizenSummary")
            or ic.get("Citizen summary")
            or ic.get("citizen_summary")
            or ap.get("Citizen summary")
            or ap.get("citizen_summary")
        )

        notes: List[str] = []
        fixes: List[str] = []

        goal = ic.get("Goal") or ic.get("goal")
        deliverable = ic.get("Deliverable") or ic.get("deliverable")
        success_metrics = ic.get("Success metrics") or ic.get("success_metrics")

        checklist = ap.get("Execution checklist") or ap.get("checklist") or ap.get("Checklist")

        required = [
            ("IC.Goal", goal),
            ("IC.Deliverable", deliverable),
            ("IC.Success metrics", success_metrics),
        ]
        missing = _count_missing_required(required)

        if missing:
            notes.append(f"Missing required fields: {', '.join(missing)}")
            fixes.append("เติม IC: Goal/Deliverable/Success metrics เพื่อความชัดเจนระดับ 1 หน้า")

        if not _is_nonempty_str(citizen_summary):
            notes.append("Citizen-facing summary not found.")
            fixes.append("เพิ่ม Citizen Summary (ย่อ 8–12 บรรทัด) อธิบายผลลัพธ์/ขั้นตอน/สิทธิอุทธรณ์")

        if not checklist:
            notes.append("Execution checklist missing — hard to operationalize.")
            fixes.append("เพิ่ม Execution checklist สำหรับเจ้าหน้าที่ (ขั้นตอนสั้น ๆ ใช้งานได้จริง)")

        score = self._score_from(missing=len(missing), penalties=0.1 if not citizen_summary else 0.0)
        verdict = "PASS" if len(missing) == 0 and _is_nonempty_str(citizen_summary) else "FAIL"

        return GateResult("Clarity Gate", verdict, notes, fixes, score)

    # -------------------------
    # Utilities
    # -------------------------
    def _summary(self, overall: Verdict, gate_results: List[GateResult]) -> str:
        if overall == "PASS":
            return "PASS — All audit gates satisfied. Deployment permitted (staged execution still recommended)."
        failed = [gr.gate for gr in gate_results if gr.verdict == "FAIL"]
        return f"FAIL — Deployment blocked. Failed gates: {', '.join(failed)}."

    def _score_from(self, missing: int, penalties: float = 0.0) -> float:
        # simple heuristic: start at 1, subtract per missing + penalties
        score = 1.0 - min(1.0, (missing * 0.18) + penalties)
        return max(0.0, score)
