"""GIS Haversine Distance Engine for Q-Transplant v4.
Calculates real geographic distance between hospitals and estimates
organ transport time to adjust cold ischemic viability window.
"""
import math
from typing import Optional

# Max safe road speed (km/hr) for organ transport, by organ urgency
TRANSPORT_SPEED = {
    "Heart":    300.0,   # Air ambulance (critical 4-6hr window)
    "Lungs":    250.0,   # Air ambulance
    "Liver":    120.0,   # Road + air hybrid
    "Pancreas": 100.0,   # Road transport viable
    "Kidney":   80.0,    # Road transport (24-36hr window)
    "Cornea":   60.0,    # Not time-critical, road transport
}

# Indian state capital coordinates (lat, lon)
STATE_COORDINATES = {
    "Delhi NCR":        (28.6139, 77.2090),
    "Tamil Nadu":       (13.0827, 80.2707),
    "Maharashtra":      (19.0760, 72.8777),
    "Karnataka":        (12.9716, 77.5946),
    "Telangana":        (17.3850, 78.4867),
    "Gujarat":          (23.0225, 72.5714),
    "Rajasthan":        (26.9124, 75.7873),
    "West Bengal":      (22.5726, 88.3639),
    "Uttar Pradesh":    (26.8467, 80.9462),
    "Madhya Pradesh":   (23.2599, 77.4126),
    "Punjab":           (30.7333, 76.7794),
    "Haryana":          (30.7333, 76.7794),
    "Bihar":            (25.5941, 85.1376),
    "Odisha":           (20.2961, 85.8245),
    "Assam":            (26.1445, 91.7362),
    "Kerala":           (8.5241, 76.9366),
    "Andhra Pradesh":   (15.9129, 79.7400),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km (Haversine formula)."""
    R = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_coords_for_state(state: str) -> Optional[tuple]:
    """Return (lat, lon) for a given Indian state name, with fuzzy match."""
    state_clean = (state or "").strip()
    # Exact match first
    if state_clean in STATE_COORDINATES:
        return STATE_COORDINATES[state_clean]
    # Partial match
    for key, val in STATE_COORDINATES.items():
        if key.lower() in state_clean.lower() or state_clean.lower() in key.lower():
            return val
    return None


def estimate_transport_hours(distance_km: float, organ_type: str) -> float:
    """Estimate hours required to transport organ given distance and organ type."""
    speed = TRANSPORT_SPEED.get(organ_type, 100.0)
    base_hours = distance_km / speed
    # Add 0.5hr overhead for loading, handover, paperwork
    return round(base_hours + 0.5, 2)


def compute_gis_adjusted_viability(
    stored_viability_hours: float,
    donor_lat: Optional[float],
    donor_lon: Optional[float],
    recipient_lat: Optional[float],
    recipient_lon: Optional[float],
    organ_type: str,
    donor_state: str = "",
    recipient_state: str = "",
) -> dict:
    """
    Returns GIS-adjusted viability remaining after estimated transport time.

    Falls back to state-capital coordinates if exact lat/lon not available.
    Returns dict with distance_km, transport_hours, adjusted_viability_hours, is_viable.
    """
    # If recipient info is completely unknown (e.g. ROOT user with no hospital),
    # skip GIS entirely — return stored viability unchanged
    no_recipient = (recipient_lat is None and recipient_lon is None and not (recipient_state or "").strip())
    if no_recipient:
        return {
            "distance_km": None,
            "transport_hours": None,
            "adjusted_viability_hours": stored_viability_hours,
            "is_viable": stored_viability_hours > 0,
            "gis_available": False,
        }

    if d_lat is None or d_lon is None:
        coords = get_coords_for_state(donor_state)
        if coords:
            d_lat, d_lon = coords

    if r_lat is None or r_lon is None:
        coords = get_coords_for_state(recipient_state)
        if coords:
            r_lat, r_lon = coords

    # If still no coords, return stored viability unchanged
    if None in (d_lat, d_lon, r_lat, r_lon):
        return {
            "distance_km": None,
            "transport_hours": None,
            "adjusted_viability_hours": stored_viability_hours,
            "is_viable": stored_viability_hours > 0,
            "gis_available": False,
        }

    distance_km = round(haversine_km(d_lat, d_lon, r_lat, r_lon), 1)
    transport_hours = estimate_transport_hours(distance_km, organ_type)
    adjusted = round(stored_viability_hours - transport_hours, 2)

    return {
        "distance_km": distance_km,
        "transport_hours": transport_hours,
        "adjusted_viability_hours": max(0.0, adjusted),
        "is_viable": adjusted > 0,
        "gis_available": True,
    }
