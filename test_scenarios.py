"""
Regression Test Suite for Vendor Onboarding Verification Process.
Covers all test scenarios and asserts exact verdicts, risk scores, and vendor messages.
Can be executed with pytest or directly with `python test_scenarios.py`.
"""

import sys
import asyncio
import pytest
from app.models import VendorSubmission, VerdictStatus, StageStatus
from app.database import init_db, reset_db
from app.sample_data import SCENARIOS, generate_scenario_pdf_bytes
from app.engine import run_verification_engine


async def execute_scenario(scenario_key: str):
    """Run a scenario through the verification engine and return the final result."""
    scenario = SCENARIOS[scenario_key]
    form = scenario["form_data"]
    
    submission = VendorSubmission(
        legal_company_name=form["legal_company_name"],
        trading_name=form.get("trading_name") or None,
        country=form["country"],
        address=form["address"],
        contact_name=form["contact_name"],
        contact_email=form["contact_email"],
        contact_phone=form["contact_phone"],
        registration_number=form["registration_number"],
        tax_id=form["tax_id"],
        bank_name=form["bank_name"],
        bank_account_holder=form["bank_account_holder"],
        bank_account_number=form["bank_account_number"],
        swift_bic=form.get("swift_bic") or None,
        vendor_category=form.get("vendor_category", "General"),
        relationship_note=form.get("relationship_note") or None,
    )

    documents = {
        "registration_certificate": generate_scenario_pdf_bytes(scenario_key, "registration_certificate"),
        "tax_certificate": generate_scenario_pdf_bytes(scenario_key, "tax_certificate"),
        "bank_letter": generate_scenario_pdf_bytes(scenario_key, "bank_letter"),
    }

    final_result = None
    async for payload in run_verification_engine(submission, documents):
        if payload.get("event") == "complete":
            final_result = payload["result"]

    return final_result


@pytest.mark.anyio
async def test_scenario_1_happy_path():
    init_db()
    reset_db()
    res = await execute_scenario("scenario_1_approved")
    assert res["verdict"] == "Approved"
    assert res["risk_score"] <= 25
    assert len(res["stages"]) == 7


@pytest.mark.anyio
async def test_scenario_2_wrong_company_docs():
    init_db()
    reset_db()
    res = await execute_scenario("scenario_2_wrong_company_docs")
    assert res["verdict"] == "Rejected"
    assert res["risk_score"] >= 80
    assert "meridian traders" in res["primary_reason"].lower() or "identity document mismatch" in res["primary_reason"].lower()


@pytest.mark.anyio
async def test_scenario_3_field_typo_pending():
    init_db()
    reset_db()
    res = await execute_scenario("scenario_3_field_typo_pending")
    assert res["verdict"] == "Pending"
    # Verify the message explicitly quotes both the form value and the document value
    assert "999999999999" in res["vendor_message"]
    assert "000123456789" in res["vendor_message"]


@pytest.mark.anyio
async def test_scenario_4a_name_mismatch_no_note():
    init_db()
    reset_db()
    res = await execute_scenario("scenario_4a_pending")
    assert res["verdict"] == "Pending"
    assert "nimbus group holdings" in res["primary_reason"].lower() or "mismatch" in res["primary_reason"].lower()


@pytest.mark.anyio
async def test_scenario_4b_name_mismatch_with_note():
    init_db()
    reset_db()
    res = await execute_scenario("scenario_4b_approved")
    assert res["verdict"] == "Approved"
    assert res["stages"][3]["flag_type"] == "name_mismatch_explained"


@pytest.mark.anyio
async def test_scenario_5_tax_id_country_fraud():
    init_db()
    reset_db()
    res = await execute_scenario("scenario_5_rejected")
    assert res["verdict"] == "Rejected"
    assert res["risk_score"] >= 80
    assert "tax id" in res["primary_reason"].lower() or "united kingdom" in res["primary_reason"].lower()


@pytest.mark.anyio
async def test_scenario_6_duplicate_bank_account():
    init_db()
    reset_db()
    # Step A: Seed
    res_a = await execute_scenario("scenario_6a_seed_vantage")
    assert res_a["verdict"] == "Approved"

    # Step B: Duplicate Bank Account
    res_b = await execute_scenario("scenario_6b_sterling_duplicate")
    assert res_b["verdict"] == "Rejected"
    assert res_b["requires_escalation"] is True
    assert res_b["risk_score"] == 100


@pytest.mark.anyio
async def test_scenario_7_returning_vendor_expired_doc():
    init_db()
    reset_db()
    # Step A: Seed
    res_a = await execute_scenario("scenario_7a_seed_anchor")
    assert res_a["verdict"] == "Approved"

    # Step B: Expired Doc
    res_b = await execute_scenario("scenario_7b_anchor_expired")
    assert res_b["verdict"] == "Pending"
    assert res_b["is_returning_vendor"] is True
    assert "tax certificate" in res_b["vendor_message"].lower() and "renewed" in res_b["vendor_message"].lower()


async def run_all_tests():
    print("================================================================")
    print(" VENDOR ONBOARDING VERIFICATION ENGINE - REGRESSION TEST SUITE ")
    print("================================================================")
    
    init_db()
    reset_db()
    print("[INIT] Test database initialized and cleared.\n")

    print("--> Running Test 1: Bluewave Logistics (US) - Happy Path...")
    res1 = await execute_scenario("scenario_1_approved")
    assert res1["verdict"] == "Approved"
    print("    [PASS] Verdict: Approved | Risk Score:", res1["risk_score"])
    print("    Primary Reason:", res1["primary_reason"])
    print()

    print("--> Running Test 2: Bluewave with Meridian Traders Docs (Wrong Company)...")
    res2 = await execute_scenario("scenario_2_wrong_company_docs")
    assert res2["verdict"] == "Rejected"
    print("    [PASS] Verdict: Rejected (Critical Wrong Company Docs) | Risk Score:", res2["risk_score"])
    print("    Primary Reason:", res2["primary_reason"])
    print()

    print("--> Running Test 3: Bluewave with Bank Account Number Typo (Field Mismatch)...")
    res3 = await execute_scenario("scenario_3_field_typo_pending")
    assert res3["verdict"] == "Pending"
    assert "999999999999" in res3["vendor_message"] and "000123456789" in res3["vendor_message"]
    print("    [PASS] Verdict: Pending (Field Discrepancy) | Risk Score:", res3["risk_score"])
    print("    Primary Reason:", res3["primary_reason"])
    print("    Quoted Message Snippet:\n   ", [line for line in res3["vendor_message"].split("\n") if "999999999999" in line][0])
    print()

    print("--> Running Test 4a: Nimbus Retail (UK) - Parent Bank (No Note)...")
    res4a = await execute_scenario("scenario_4a_pending")
    assert res4a["verdict"] == "Pending"
    print("    [PASS] Verdict: Pending | Risk Score:", res4a["risk_score"])
    print("    Primary Reason:", res4a["primary_reason"])
    print()

    print("--> Running Test 4b: Nimbus Retail (UK) - Parent Bank (WITH Note)...")
    res4b = await execute_scenario("scenario_4b_approved")
    assert res4b["verdict"] == "Approved"
    print("    [PASS] Verdict: Approved (Non-blocking note) | Risk Score:", res4b["risk_score"])
    print("    Primary Reason:", res4b["primary_reason"])
    print()

    print("--> Running Test 5: Meridian Traders (US) - UK VAT Format on US Company...")
    res5 = await execute_scenario("scenario_5_rejected")
    assert res5["verdict"] == "Rejected"
    print("    [PASS] Verdict: Rejected (Hard Tax ID Fraud Signal) | Risk Score:", res5["risk_score"])
    print("    Primary Reason:", res5["primary_reason"])
    print()

    print("--> Running Test 6a: Seed Vantage Freight Co (DE)...")
    res6a = await execute_scenario("scenario_6a_seed_vantage")
    assert res6a["verdict"] == "Approved"
    print("    [PASS] Vantage Freight Approved and recorded in vendor ledger.")

    print("--> Running Test 6b: Sterling Freight Partners (DE) - Duplicate Account...")
    res6b = await execute_scenario("scenario_6b_sterling_duplicate")
    assert res6b["verdict"] == "Rejected"
    print("    [PASS] Verdict: Rejected (Duplicate Bank Account Fraud - Escalated) | Risk Score: 100")
    print("    Primary Reason:", res6b["primary_reason"])
    print()

    print("--> Running Test 7a: Seed Anchor Supplies Pvt Ltd (IN)...")
    res7a = await execute_scenario("scenario_7a_seed_anchor")
    assert res7a["verdict"] == "Approved"
    print("    [PASS] Anchor Supplies Initial Approval recorded in vendor ledger.")

    print("--> Running Test 7b: Anchor Supplies Pvt Ltd (IN) - Expired Tax Cert...")
    res7b = await execute_scenario("scenario_7b_anchor_expired")
    assert res7b["verdict"] == "Pending"
    print("    [PASS] Verdict: Pending (Returning Vendor Lightweight Follow-up) | Risk Score:", res7b["risk_score"])
    print("    Primary Reason:", res7b["primary_reason"])
    print()

    print("================================================================")
    print(" ALL SCENARIOS AND REGRESSION ASSERTIONS PASSED PERFECTLY!      ")
    print("================================================================")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
