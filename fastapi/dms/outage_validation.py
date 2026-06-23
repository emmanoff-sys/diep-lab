"""DIEP ADMS P6-M8 — Outage Inference Validation Hooks.

Cross-check the M7 outage inference against the M5 N-1 contingency model and *flag*
inconsistencies — it does NOT auto-resolve them. The two are computed independently:
M7 from live AMI last-gasp signals + topology, M5 from a what-if outage of each
element. Where M7's probable device corresponds to an M5 element, their
affected-customer counts and restorability should agree; divergence usually means a
model/telemetry gap worth a human's attention (stale topology, missing service
points, a tie that would have back-fed, a device M5 doesn't model).

Pure function over the two structured outputs. Read-only.
"""
from __future__ import annotations


def cross_check(inferred_outages: list[dict], contingencies: list[dict],
                options: dict | None = None) -> dict:
    opt = options or {}
    tol = int(opt.get("customer_tolerance", 0))
    by_elem = {c["element"]: c for c in contingencies}

    checks = []
    for o in inferred_outages:
        dev = o.get("probable_device")
        eid = dev["edge_id"] if dev else None
        inf_cust = o.get("estimated_customers_affected", 0)
        flags: list[str] = []
        n1 = None

        if eid is None:
            flags.append("whole_feeder_outage_no_single_element")
        else:
            n1 = by_elem.get(eid)
            if n1 is None:
                flags.append("inferred_device_not_in_n1_model")
            else:
                n1_lost = n1.get("lost_customers", 0)
                if abs(inf_cust - n1_lost) > tol:
                    flags.append("customer_count_mismatch")
                if n1.get("restored_by"):
                    flags.append("restorable_via_tie")  # actionable, not an error
                if n1.get("classification") in ("unserved", "partial"):
                    flags.append("n1_confirms_unserved")
                if n1.get("post_violations", 0) > 0:
                    flags.append("post_contingency_violation")

        checks.append({
            "section_node": o.get("section_node"),
            "inferred_device": eid,
            "inferred_customers": inf_cust,
            "inference_confidence": o.get("confidence"),
            "n1_element_found": n1 is not None,
            "n1_lost_customers": (n1.get("lost_customers") if n1 else None),
            "n1_classification": (n1.get("classification") if n1 else None),
            "n1_restorable_by": (n1.get("restored_by") if n1 else None),
            "flags": flags,
            # a real disagreement (vs merely-informational flags)
            "mismatch": any(f in ("customer_count_mismatch", "inferred_device_not_in_n1_model")
                            for f in flags),
        })

    mismatches = [c for c in checks if c["mismatch"]]
    return {
        "method": "cross-check M7 outage inference vs M5 N-1 contingency; flag only",
        "checks": checks,
        "consistent": not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }
