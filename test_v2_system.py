import requests
import json

BASE_URL = "http://127.0.0.1:8000/api/v1"

def test_system():
    print("--- 1. Testing Root Login ---")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "aravindhkmc@gmail.com",
        "password": "1234"
    })
    print(f"Login Status: {resp.status_code}")
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    token = data["access_token"]
    print(f"Token acquired. Role: {data.get('role')}")

    headers = {"Authorization": f"Bearer {token}"}

    print("\n--- 2. Testing Hospital-Wise Datasets Endpoint ---")
    resp_ds = requests.get(f"{BASE_URL}/organizer/hospital-datasets", headers=headers)
    print(f"Hospital Datasets Status: {resp_ds.status_code}")
    assert resp_ds.status_code == 200, f"Datasets fetch failed: {resp_ds.text}"
    ds_data = resp_ds.json()
    hospitals = ds_data.get("hospitals", []) if isinstance(ds_data, dict) else ds_data
    print(f"Found {len(hospitals)} registered hospitals.")
    for h in hospitals[:3]:
        print(f" - Hospital: {h['hospital_name']} (Reg: {h['registration_number']}, State: {h['state']}), Donors: {len(h.get('donors', []))}")

    print("\n--- 3. Testing Root CSV Dataset Ingestion ---")
    csv_content = """organ_type,blood_group,hla_a,hla_b,viability_hours_remaining,health_status
Kidney,O+,A2,B7,18,OPTIMAL
Heart,AB+,A1,B8,5,CRITICAL
Liver,A-,A3,B12,12,HEALTHY
"""
    files = {"file": ("test_donors.csv", csv_content, "text/csv")}
    resp_csv = requests.post(f"{BASE_URL}/donors/import-csv", headers=headers, files=files)
    print(f"CSV Ingestion Status: {resp_csv.status_code}")
    assert resp_csv.status_code == 200, f"CSV ingestion failed: {resp_csv.text}"
    print(f"Ingestion result: {resp_csv.json()}")

    print("\n--- 4. Testing Organ Match Search ---")
    resp_match = requests.post(f"{BASE_URL}/matching/search", headers=headers, json={
        "organ_type": "Kidney",
        "blood_group": "O+"
    })
    print(f"Match Search Status: {resp_match.status_code}")
    assert resp_match.status_code == 200, f"Match search failed: {resp_match.text}"
    match_data = resp_match.json()
    matches = match_data.get("matches", [])
    print(f"Matches Found: {len(matches)}")
    if matches:
        top = matches[0]
        print(f"Top Match: {top['organ_type']} from {top['holding_hospital']['hospital_name']} with Efficiency Score: {top['efficiency_score_percentage']}%")

    print("\n✅ ALL SYSTEM VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_system()
