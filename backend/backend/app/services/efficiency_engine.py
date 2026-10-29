"""Q-Transplant v4 — Multi-Factor Match Efficiency Engine.

Clinically accurate scoring weights:
  Blood Group (ABO/Rh)   : 25%  — hard gate, then exact vs compatible bonus
  HLA 6-locus matching   : 40%  — DR=12, A=8, B=8, DQ=6, C=4, DP=2 (clinical weight order)
  Viability (GIS-decay'd): 20%  — based on GIS-adjusted hours remaining
  Waiting Time           :  8%  — months on waiting list (0-8 scale)
  Urgency Level          :  5%  — CRITICAL=5, HIGH=3, MEDIUM=1
  PRA Crossmatch Penalty :  0 to -25 — high sensitization reduces confidence
"""

# ─── Blood Group Compatibility Matrix ───────────────────────────────────────
# Donor → list of compatible Recipient blood groups
BLOOD_COMPATIBILITY = {
    "O-":  ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],
    "O+":  ["O+", "A+", "B+", "AB+"],
    "A-":  ["A-", "A+", "AB-", "AB+"],
    "A+":  ["A+", "AB+"],
    "B-":  ["B-", "B+", "AB-", "AB+"],
    "B+":  ["B+", "AB+"],
    "AB-": ["AB-", "AB+"],
    "AB+": ["AB+"],
}

# HLA clinical weights (total = 40%)
HLA_WEIGHTS = {
    "hla_dr": 12.0,   # Strongest predictor of rejection
    "hla_a":   8.0,
    "hla_b":   8.0,
    "hla_dq":  6.0,
    "hla_c":   4.0,
    "hla_dp":  2.0,   # Optional locus
}


def is_blood_compatible(donor_blood: str, recipient_blood: str) -> bool:
    d = (donor_blood or "").strip().upper()
    r = (recipient_blood or "").strip().upper()
    return r in BLOOD_COMPATIBILITY.get(d, [])


def score_hla_match(donor: dict, recipient: dict) -> dict:
    """Score HLA compatibility using clinical locus weights.

    Returns dict with per-locus results and total hla_score (0-40).
    """
    total_score = 0.0
    max_possible = 0.0
    per_locus = {}

    for locus, weight in HLA_WEIGHTS.items():
        d_val = (donor.get(locus) or "").strip().upper()
        r_val = (recipient.get(locus) or "").strip().upper()

        if not d_val or not r_val:
            # Unknown locus — award 60% of weight (neutral assumption)
            awarded = weight * 0.6
            per_locus[locus] = {"result": "UNKNOWN", "awarded": awarded, "weight": weight}
            total_score += awarded
            max_possible += weight
            continue

        max_possible += weight

        if d_val == r_val:
            # Full match
            awarded = weight
            per_locus[locus] = {"result": "FULL_MATCH", "awarded": awarded, "weight": weight}
        elif d_val[:2] == r_val[:2]:
            # Same allele family (e.g. A2 vs A24 — partial)
            awarded = weight * 0.5
            per_locus[locus] = {"result": "PARTIAL_MATCH", "awarded": awarded, "weight": weight}
        else:
            awarded = 0.0
            per_locus[locus] = {"result": "MISMATCH", "awarded": 0.0, "weight": weight}

        total_score += awarded

    hla_pct = round((total_score / 40.0) * 100.0, 1) if max_possible > 0 else 75.0
    return {
        "hla_score": round(total_score, 2),
        "hla_percentage": hla_pct,
        "per_locus": per_locus,
    }


def score_viability(adjusted_hours: float, organ_type: str) -> float:
    """Score organ viability after GIS-transport-adjusted hours (0-20 pts)."""
    # Organ-specific maximum viable windows
    MAX_HOURS = {
        "Heart": 6, "Lungs": 8, "Liver": 24,
        "Pancreas": 18, "Kidney": 36, "Cornea": 168,
    }
    organ_max = MAX_HOURS.get(organ_type, 24)
    ratio = max(0.0, adjusted_hours / organ_max)

    if ratio >= 0.75:   return 20.0
    elif ratio >= 0.5:  return 15.0
    elif ratio >= 0.25: return 10.0
    elif ratio > 0:     return 5.0
    else:               return 0.0  # Organ expired


def score_waiting_time(registered_at) -> float:
    """Score based on how long recipient has been waiting (0-8 pts)."""
    if registered_at is None:
        return 4.0  # Neutral
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    # Handle naive datetimes
    if registered_at.tzinfo is None:
        registered_at = registered_at.replace(tzinfo=timezone.utc)
    months_waiting = (now - registered_at).days / 30.0
    if months_waiting >= 24:    return 8.0
    elif months_waiting >= 12:  return 6.0
    elif months_waiting >= 6:   return 4.0
    elif months_waiting >= 3:   return 2.0
    else:                       return 1.0


def score_urgency(urgency_level: str) -> float:
    """Score urgency level (0-5 pts)."""
    return {"CRITICAL": 5.0, "HIGH": 3.0, "MEDIUM": 1.0}.get(
        (urgency_level or "HIGH").upper(), 3.0
    )


def pra_crossmatch_penalty(pra_percentage: float) -> dict:
    """Calculate crossmatch risk penalty based on Panel Reactive Antibody %.

    PRA > 80% = very high sensitization → high rejection risk.
    Returns penalty points (negative) and risk label.
    """
    pra = float(pra_percentage or 0.0)
    if pra >= 85:
        return {"penalty": -20.0, "risk": "VERY_HIGH", "flag": True,
                "message": "PRA ≥85%: Very high crossmatch risk. Virtual crossmatch required before transplant."}
    elif pra >= 70:
        return {"penalty": -12.0, "risk": "HIGH", "flag": True,
                "message": "PRA ≥70%: High sensitization. Physical crossmatch mandatory."}
    elif pra >= 50:
        return {"penalty": -5.0, "risk": "MODERATE", "flag": False,
                "message": "PRA ≥50%: Moderate sensitization. Crossmatch recommended."}
    else:
        return {"penalty": 0.0, "risk": "LOW", "flag": False, "message": "PRA <50%: Low crossmatch risk."}


def calculate_match_efficiency(donor: dict, recipient: dict,
                               gis_data: dict = None,
                               waiting_registered_at=None,
                               urgency_level: str = "HIGH",
                               pra_percentage: float = 0.0) -> dict:
    """
    Full clinical match efficiency score (0–100%).

    donor / recipient dicts must include:
      organ_type, blood_group, hla_a/b/c/dr/dq, viability_hours_remaining, health_status

    gis_data: output from gis_engine.compute_gis_adjusted_viability()
    """
    # ── 1. Organ Type Gate ─────────────────────────────────────────────────
    d_organ = (donor.get("organ_type") or "").strip().lower()
    r_organ = (recipient.get("organ_type") or "").strip().lower()
    if d_organ != r_organ:
        return {"efficiency_score": 0.0, "is_compatible": False,
                "reason": f"Organ type mismatch: donor={d_organ}, recipient={r_organ}"}

    # ── 2. Blood Group (25%) ───────────────────────────────────────────────
    d_blood = (donor.get("blood_group") or "O+").strip().upper()
    r_blood = (recipient.get("blood_group") or "O+").strip().upper()
    blood_ok = is_blood_compatible(d_blood, r_blood)

    if not blood_ok:
        return {"efficiency_score": 0.0, "is_compatible": False,
                "reason": f"ABO incompatible: donor={d_blood}, recipient={r_blood}"}

    blood_score = 25.0 if d_blood == r_blood else 20.0  # Exact vs compatible

    # ── 3. HLA 6-Locus (40%) ──────────────────────────────────────────────
    hla_result = score_hla_match(donor, recipient)
    hla_score = hla_result["hla_score"]

    # ── 4. Viability after GIS decay (20%) ────────────────────────────────
    if gis_data and gis_data.get("gis_available"):
        adj_hours = gis_data["adjusted_viability_hours"]
    else:
        adj_hours = float(donor.get("viability_hours_remaining") or 24.0)

    viability_score = score_viability(adj_hours, donor.get("organ_type", "Kidney"))

    # ── 5. Waiting Time (8%) ──────────────────────────────────────────────
    wait_score = score_waiting_time(waiting_registered_at)

    # ── 6. Urgency (5%) ───────────────────────────────────────────────────
    urgency_score = score_urgency(urgency_level)

    # ── 7. PRA Crossmatch Penalty ─────────────────────────────────────────
    pra_result = pra_crossmatch_penalty(pra_percentage)
    penalty = pra_result["penalty"]

    # ── Total ──────────────────────────────────────────────────────────────
    raw_total = blood_score + hla_score + viability_score + wait_score + urgency_score + penalty
    total = round(min(99.9, max(5.0, raw_total)), 1)

    return {
        "efficiency_score": total,
        "is_compatible": True,
        "blood_match": blood_ok,
        "blood_score": blood_score,
        "hla_score": hla_score,
        "hla_percentage": hla_result["hla_percentage"],
        "hla_per_locus": hla_result["per_locus"],
        "viability_score": viability_score,
        "adjusted_viability_hours": adj_hours,
        "gis_available": gis_data.get("gis_available", False) if gis_data else False,
        "distance_km": gis_data.get("distance_km") if gis_data else None,
        "transport_hours": gis_data.get("transport_hours") if gis_data else None,
        "wait_score": wait_score,
        "urgency_score": urgency_score,
        "pra_risk": pra_result["risk"],
        "pra_flag": pra_result["flag"],
        "pra_message": pra_result["message"],
        "pra_penalty": penalty,
    }
