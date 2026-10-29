import requests
import json

BASE_URL = "http://127.0.0.1:8000/api/v1"

def test_enterprise_v3():
    print("--- 1. Root Login ---")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "aravindhkmc@gmail.com",
        "password": "1234"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Authenticated as Root Organizer")

    print("\n--- 2. Fetching Hospital-Wise Datasets ---")
    resp_ds = requests.get(f"{BASE_URL}/organizer/hospital-datasets", headers=headers)
    assert resp_ds.status_code == 200
    hospitals = resp_ds.json()
    print(f"✅ Found {len(hospitals)} registered hospitals.")

    donor_id = None
    for h in hospitals:
        if h.get("donors"):
            donor_id = h["donors"][0]["id"]
            break

    assert donor_id is not None, "No donor records found to test FHIR export."

    print(f"\n--- 3. Testing HL7 FHIR R4 Donor Bundle Export (Donor ID: {donor_id}) ---")
    resp_fhir = requests.get(f"{BASE_URL}/fhir/donors/{donor_id}")
    assert resp_fhir.status_code == 200, f"FHIR Export failed: {resp_fhir.text}"
    fhir_data = resp_fhir.json()
    assert fhir_data.get("resourceType") == "Bundle"
    print(f"✅ HL7 FHIR R4 Specimen Bundle successfully generated! Resource Type: {fhir_data['resourceType']}, Entries: {len(fhir_data['entry'])}")

    print("\n--- 4. Testing Organ Match Engine Search & Ledger Logging ---")
    resp_match = requests.post(f"{BASE_URL}/matching/search", headers=headers, json={
        "organ_type": "Kidney",
        "blood_group": "O+"
    })
    assert resp_match.status_code == 200

    print("\n--- 5. Testing SHA-256 Cryptographic Audit Ledger ---")
    resp_ledger = requests.get(f"{BASE_URL}/organizer/audit-ledger", headers=headers)
    assert resp_ledger.status_code == 200, f"Ledger fetch failed: {resp_ledger.text}"
    ledger_data = resp_ledger.json()
    assert ledger_data["chain_valid"] is True, "Cryptographic ledger hash chain is invalid!"
    print(f"✅ Cryptographic Ledger Verified! Total Blocks: {ledger_data['total_blocks']}, Chain Valid: {ledger_data['chain_valid']}")
    latest_block = ledger_data["ledger"][-1]
    print(f"   Latest Block #{latest_block['index']} Action: {latest_block['action']} Hash: {latest_block['hash'][:24]}...")

    print("\n🎉 ALL ENTERPRISE V3 FEASIBILITY & RELIABILITY TESTS PASSED WITH 100% SUCCESS!")

if __name__ == "__main__":
    test_enterprise_v3()
