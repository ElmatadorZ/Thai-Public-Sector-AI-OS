CIVIC-OS Metrics Module
- Normalizes metrics
- Validates required fields
- Computes deltas vs baseline (absolute + % change)
- Provides helpers for thresholds & reporting

Design goals:
- Deterministic, portable, no external deps
- Safe defaults: missing metrics flagged
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_REQUIRED_METRICS = [
    "service_latency_median",
    "service_latency_p90",
    "throughput",
    "error_rate",
    "transparency_coverage",
    "citizen_burden_index",
    "disparity_index",
]


def _num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
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


@dataclass
class MetricsValidation:
    ok: bool
    missing: List[str] = field(default_factory=list)
    non_numeric: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "missing": self.missing,
            "non_numeric": self.non_numeric,
            "notes": self.notes,
        }


@dataclass
class MetricsDelta:
    current: Dict[str, Any]
    baseline: Optional[Dict[str, Any]]
    absolute: Dict[str, Optional[float]]
    pct: Dict[str, Optional[float]]
    validation: MetricsValidation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validation": self.validation.to_dict(),
            "absolute": self.absolute,
            "pct": self.pct,
            "current": self.current,
            "baseline": self.baseline,
        }


class Metrics:
    def __init__(self, required_metrics: Optional[List[str]] = None):
        self.required_metrics = required_metrics or list(DEFAULT_REQUIRED_METRICS)

    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize known metric keys to floats where possible; keep others as-is.
        """
        out: Dict[str, Any] = dict(raw or {})
        for k, v in list(out.items()):
            if k in self.required_metrics or k.endswith("_index") or k.endswith("_rate") or k.endswith("_coverage"):
                n = _num(v)
                out[k] = n if n is not None else v
        return out

    def validate(self, current: Dict[str, Any], baseline: Optional[Dict[str, Any]] = None) -> MetricsValidation:
        cur = current or {}
        missing = [k for k in self.required_metrics if k not in cur or cur.get(k) is None]
        non_numeric: List[str] = []
        for k in self.required_metrics:
            if k in cur and cur.get(k) is not None:
                if _num(cur.get(k)) is None:
                    non_numeric.append(k)

        notes = []
        if baseline is None:
            notes.append("Baseline missing: pct deltas may be unavailable. (OK for exploratory pilots.)")

        ok = len(missing) == 0 and len(non_numeric) == 0
        return MetricsValidation(ok=ok, missing=missing, non_numeric=non_numeric, notes=notes)

    def compute_deltas(self, current: Dict[str, Any], baseline: Optional[Dict[str, Any]] = None) -> MetricsDelta:
        cur = self.normalize(current or {})
        base = self.normalize(baseline or {}) if baseline else None

        validation = self.validate(cur, base)
        absolute: Dict[str, Optional[float]] = {}
        pct: Dict[str, Optional[float]] = {}

        for k in set(list(cur.keys()) + (list(base.keys()) if base else [])):
            c = _num(cur.get(k))
            b = _num(base.get(k)) if base else None
            if c is not None and b is not None:
                absolute[k] = c - b
                pct[k] = _pct_change(c, b)
            else:
                absolute[k] = None if c is None or b is None else c - b
                pct[k] = _pct_change(c, b)

        return MetricsDelta(
            current=cur,
            baseline=base,
            absolute=absolute,
            pct=pct,
            validation=validation,
        )

    @staticmethod
    def explain_key_metrics() -> Dict[str, str]:
        return {
            "service_latency_median": "Median time to completion (days/hours).",
            "service_latency_p90": "90th percentile completion time (tail latency).",
            "throughput": "Cases completed per time window.",
            "error_rate": "Fraction of cases requiring rework / incorrect decisions.",
            "transparency_coverage": "Fraction of steps with traceable logs (0..1).",
            "citizen_burden_index": "Composite proxy for steps/docs/trips/cost (baseline=1.0).",
            "disparity_index": "Composite fairness gap proxy (baseline=1.0).",
            "shadow_paperwork_index": "Proxy for off-system work (baseline=1.0).",
        }
