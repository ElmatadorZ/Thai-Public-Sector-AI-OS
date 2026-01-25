#import json
import sys
from civic_os.orchestrator import CivicOSOrchestrator, RunInput

def main():
    task = " ".join(sys.argv[1:]) or "Redesign a permit application service to reduce p90 latency"
    orch = CivicOSOrchestrator()

    # Example metrics (edit these to simulate monitoring)
    baseline = {
        "service_latency_median": 10,
        "service_latency_p90": 30,
        "throughput": 120,
        "error_rate": 0.08,
        "transparency_coverage": 0.55,
        "citizen_burden_index": 1.00,
        "disparity_index": 1.00,
        "shadow_paperwork_index": 1.00,
    }
    current = {
        "service_latency_median": 8,   # improved
        "service_latency_p90": 26,
        "throughput": 135,
        "error_rate": 0.10,            # worsened (may trigger falsifier depending thresholds)
        "transparency_coverage": 0.58,
        "citizen_burden_index": 1.05,
        "disparity_index": 1.02,
        "shadow_paperwork_index": 1.00,
    }

    res = orch.run(
        RunInput(
            task=task,
            domain="service_latency",
            window="weekly",
            metrics_baseline=baseline,
            metrics_current=current,
        )
    )

    print("\n=== CIVIC-OS RUN RESULT ===")
    print("run_id:", res.run_id)
    print("audit_overall:", res.audit_overall)
    print("falsifier_verdict:", res.falsifier_verdict)
    print("run_dir:", res.run_dir)
    print("signed_log_path:", res.outputs["signed_log_path"])
    print("\n--- audit_report.summary ---")
    print(res.outputs["audit_report"]["summary"])
    print("\n--- falsifier_result.summary ---")
    if res.outputs["falsifier_result"]:
        print(res.outputs["falsifier_result"]["summary"])
    else:
        print("No falsifier evaluation (metrics_current not provided).")

    # Print full JSON (optional)
    # print(json.dumps(res.outputs, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
