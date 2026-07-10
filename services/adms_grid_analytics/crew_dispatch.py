"""DIEP ADMS P6-M9 — Crew Dispatch Recommendation (read-only).

Produce a *prioritized list* of outage locations for the control room, ranked by
estimated customers affected and restoration complexity. Restoration complexity
comes from the M5 N-1 model: if the outage's device can be back-fed by a tie
(`restored_by`), it is a low-complexity **remote switch** (operator action, no
crew); otherwise it is a high-complexity **field repair** needing a crew.

This is advisory only — no actuation, no ticketing/CAD integration. It just ranks
candidates so dispatchers know where crews matter most.
"""

from __future__ import annotations


def recommend(
    inferred_outages: list[dict], contingencies: list[dict], options: dict | None = None
) -> dict:
    by_elem = {c["element"]: c for c in contingencies}

    items = []
    for o in inferred_outages:
        dev = o.get("probable_device")
        eid = dev["edge_id"] if dev else None
        n1 = by_elem.get(eid) if eid else None
        restorable = bool(n1 and n1.get("restored_by"))
        action = "remote_switch" if restorable else "dispatch_crew"
        complexity = "low (tie back-feed)" if restorable else "high (field repair)"
        customers = o.get("estimated_customers_affected", 0)
        items.append(
            {
                "section_node": o.get("section_node"),
                "section_name": o.get("section_name"),
                "probable_device": eid,
                "feeding_transformer": o.get("feeding_transformer"),
                "estimated_customers_affected": customers,
                "inference_confidence": o.get("confidence"),
                "restorable_via_tie": restorable,
                "restoration_path": (n1.get("restored_by") if n1 else []),
                "restoration_complexity": complexity,
                "recommended_action": action,
                "priority_score": customers,
            }
        )

    # Crews matter most where there's NO remote restoration; within each class rank
    # by customers affected. (Remote-switch outages are flagged as quick wins for the
    # operator, not crew work.)
    items.sort(
        key=lambda x: (
            x["recommended_action"] == "dispatch_crew",
            x["estimated_customers_affected"],
        ),
        reverse=True,
    )
    for i, it in enumerate(items, 1):
        it["priority_rank"] = i

    return {
        "method": "rank by restoration complexity (crew before remote-switch) then "
        "estimated customers affected; advisory only — no actuation/ticketing",
        "candidates": items,
        "crew_dispatch_count": sum(1 for x in items if x["recommended_action"] == "dispatch_crew"),
        "remote_switch_count": sum(1 for x in items if x["recommended_action"] == "remote_switch"),
    }
