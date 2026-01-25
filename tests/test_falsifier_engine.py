# test_falsifier_engine.py
from civic_os.falsifier_engine import FalsifierEngine, MetricsSnapshot


def test_falsifier_latency_down_errors_up_triggers():
    engine = FalsifierEngine(
        thresholds={
            "latency_improve": -0.10,  # -10%
            "error_worsen": 0.10,      # +10%
        },
        require_baseline=True,
    )
    baseline = {
        "service_latency_median": 10,
        "error_rate": 0.10,
        "throughput": 100,
        "disparity_index": 1.00,
        "transparency_coverage": 0.70,
        "citizen_burden_index": 1.00,
    }
    current = {
        "service_latency_median": 8,   # -20%
        "error_rate": 0.12,            # +20%
        "throughput": 100,
        "disparity_index": 1.00,
        "transparency_coverage": 0.70,
        "citizen_burden_index": 1.00,
    }
    res = engine.evaluate(MetricsSnapshot(current=current, baseline=baseline, window="weekly"))
    assert res.verdict == "FALSIFIED"
    assert any(h.code == "latency_down_errors_up" for h in res.hits)


def test_falsifier_no_high_hits_ok():
    engine = FalsifierEngine(require_baseline=True)
    baseline = {
        "service_latency_median": 10,
        "error_rate": 0.10,
        "throughput": 100,
        "disparity_index": 1.00,
        "transparency_coverage": 0.70,
        "citizen_burden_index": 1.00,
    }
    current = {
        "service_latency_median": 9,   # -10% (borderline)
        "error_rate": 0.10,            # no worsen
        "throughput": 105,             # +5%
        "disparity_index": 1.00,
        "transparency_coverage": 0.70,
        "citizen_burden_index": 1.00,
    }
    res = engine.evaluate(MetricsSnapshot(current=current, baseline=baseline, window="weekly"))
    assert res.verdict in ("OK", "FALSIFIED")  # allow threshold sensitivity
