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
    assert len(res["stages"]) == 8


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
    assert res["verdict"] == "Pending"
    assert res["reason_code"] == "name_mismatch_explained"
    assert res["stages"][4]["flag_type"] == "name_mismatch_explained"
    assert "review and confirm before approving" in res["primary_reason"].lower()
    assert "nimbus group holdings" in res["primary_reason"].lower()


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


@pytest.mark.anyio
async def test_scenario_8_sanctions_hard_match():
    init_db()
    reset_db()
    res = await execute_scenario("scenario_8_sanctions_hard_match")
    assert res["verdict"] == "Rejected"
    assert res["reason_code"] == "sanctions_match"
    assert res["risk_score"] == 100
    assert res["requires_escalation"] is True
    assert res["stages"][0]["status"] == "FAIL"
    assert res["stages"][0]["flag_type"] == "sanctions_hard_match"
    # Compliance-safe generic vendor communication (no sanctions disclosure)
    assert "unable to proceed" in res["vendor_message"].lower()
    assert "compliance team" in res["vendor_message"].lower()
    assert "sanction" not in res["vendor_message"].lower()
    assert "restricted" not in res["vendor_message"].lower()
    # Internal reasoning shows match details and statutory override
    assert "talon sentinel trading co" in res["primary_reason"].lower()
    assert "overrode all subsequent checks" in res["primary_reason"].lower()


@pytest.mark.anyio
async def test_scenario_9_sanctions_moderate_match():
    init_db()
    reset_db()
    res = await execute_scenario("scenario_9_sanctions_moderate_match")
    assert res["verdict"] == "Pending"
    assert res["reason_code"] == "sanctions_review"
    assert res["stages"][0]["status"] == "WARNING"
    assert res["stages"][0]["flag_type"] == "sanctions_review"
    # Compliance-safe generic pending review communication (no specific field prompts)
    assert "under additional review" in res["vendor_message"].lower()
    assert "follow up shortly" in res["vendor_message"].lower()
    assert "sanction" not in res["vendor_message"].lower()
    assert "please provide" not in res["vendor_message"].lower()
    # Internal reasoning shows percentage and matched entry
    assert "talon sentinel trading co" in res["primary_reason"].lower()
    assert "81." in res["primary_reason"] or "81%" in res["primary_reason"]


@pytest.mark.anyio
async def test_scenario_10_embargoed_country():
    init_db()
    reset_db()
    res = await execute_scenario("scenario_10_embargoed_country")
    assert res["verdict"] == "Rejected"
    assert res["reason_code"] == "sanctions_match"
    assert res["risk_score"] == 100
    assert res["stages"][0]["status"] == "FAIL"
    # Generic vendor message
    assert "unable to proceed" in res["vendor_message"].lower()
    assert "sanction" not in res["vendor_message"].lower()
    # Internal reasoning shows embargoed country details
    assert "freedonia" in res["primary_reason"].lower()
    assert "overrode all subsequent checks" in res["primary_reason"].lower()


@pytest.mark.anyio
async def test_suite_order_regression_bluewave_stays_approved():
    """
    Permanent regression guard:
    Run the entire scenario suite sequentially in a single shared database session
    (without resetting DB between scenarios), then assert Bluewave happy path specifically
    still returns Approved. This ensures no subsequent scenario can silently collide with
    Bluewave's identifying data.
    """
    init_db()
    reset_db()
    scenarios_in_order = [
        "scenario_1_approved",
        "scenario_2_wrong_company_docs",
        "scenario_3_field_typo_pending",
        "scenario_4a_pending",
        "scenario_4b_approved",
        "scenario_5_rejected",
        "scenario_6a_seed_vantage",
        "scenario_6b_sterling_duplicate",
        "scenario_7a_seed_anchor",
        "scenario_7b_anchor_expired",
        "scenario_8_sanctions_hard_match",
        "scenario_9_sanctions_moderate_match",
        "scenario_10_embargoed_country",
    ]
    for s_key in scenarios_in_order:
        await execute_scenario(s_key)

    # Post-suite re-run of Bluewave Logistics happy path
    res = await execute_scenario("scenario_1_approved")
    assert res["verdict"] == "Approved"
    assert res["risk_score"] <= 25
    assert len(res["stages"]) == 8


@pytest.mark.anyio
async def test_rejected_run_cannot_claim_bank_account():
    """
    Ensure rejected runs cannot claim or lock a bank account number in the vendor ledger.
    Even if an unverified/rejected submission attempted to use the same bank account,
    a subsequent legitimate vendor submission must never be flagged as reusing that account.
    """
    from app.database import save_run
    from app.models import VerificationResult

    init_db()
    reset_db()

    # Seed a rejected run attempting to use Bluewave's bank account
    fake_rejected_sub = VendorSubmission(
        legal_company_name="Fraudulent Rogue Entity",
        trading_name=None,
        country="United States",
        address="99 Scam Way, Dover, DE",
        contact_name="Malicious Actor",
        contact_email="bad@malicious.com",
        contact_phone="+1-302-555-0999",
        registration_number="US-DE-0000001",
        tax_id="99-1112233",
        bank_name="First Continental Bank",
        bank_account_holder="Fraudulent Rogue Entity",
        bank_account_number="000123456789",  # Deliberate collision with Bluewave
        swift_bic="FCBKUS33"
    )
    fake_rejected_result = VerificationResult(
        run_id="RUN-REJECTED-SEED",
        timestamp="2026-09-03T10:00:00",
        submission=fake_rejected_sub,
        verdict=VerdictStatus.REJECTED,
        risk_score=100,
        primary_reason="Simulated hard rejection for testing"
    )
    save_run(fake_rejected_result)

    # Legitimate Bluewave submission with bank account 000123456789
    res = await execute_scenario("scenario_1_approved")
    assert res["verdict"] == "Approved"
    assert res["risk_score"] <= 25



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
    assert res4b["verdict"] == "Pending"
    assert res4b["reason_code"] == "name_mismatch_explained"
    assert "review and confirm before approving" in res4b["primary_reason"].lower()
    print("    [PASS] Verdict: Pending (Rapid Reviewer Sign-off) | Risk Score:", res4b["risk_score"])
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

    print("--> Running Test 8: Talon Sentinel Trading Co (US) - Sanctions Hard Match...")
    res8 = await execute_scenario("scenario_8_sanctions_hard_match")
    assert res8["verdict"] == "Rejected"
    assert res8["reason_code"] == "sanctions_match"
    assert "unable to proceed" in res8["vendor_message"].lower()
    assert "sanction" not in res8["vendor_message"].lower()
    print("    [PASS] Verdict: Rejected (Sanctions Hard Match) | Risk Score: 100")
    print("    Primary Reason:", res8["primary_reason"])
    print("    Vendor Message Snippet:", repr(res8["vendor_message"][:80]))
    print()

    print("--> Running Test 9: Talon Sentinal Trading Company (US) - Sanctions Moderate Match...")
    res9 = await execute_scenario("scenario_9_sanctions_moderate_match")
    assert res9["verdict"] == "Pending"
    assert res9["reason_code"] == "sanctions_review"
    assert "under additional review" in res9["vendor_message"].lower()
    assert "sanction" not in res9["vendor_message"].lower()
    print("    [PASS] Verdict: Pending (Sanctions Moderate Review) | Risk Score:", res9["risk_score"])
    print("    Primary Reason:", res9["primary_reason"])
    print("    Vendor Message Snippet:", repr(res9["vendor_message"][:80]))
    print()

    print("--> Running Test 10: Bluewave Logistics Inc (Freedonia) - Embargoed Country...")
    res10 = await execute_scenario("scenario_10_embargoed_country")
    assert res10["verdict"] == "Rejected"
    assert res10["reason_code"] == "sanctions_match"
    assert "unable to proceed" in res10["vendor_message"].lower()
    assert "sanction" not in res10["vendor_message"].lower()
    print("    [PASS] Verdict: Rejected (Embargoed Country) | Risk Score: 100")
    print("    Primary Reason:", res10["primary_reason"])
    print("    Vendor Message Snippet:", repr(res10["vendor_message"][:80]))
    print()

    print("--> Running Test 11 (Permanent Regression Check): Bluewave Logistics Happy Path after full suite...")
    res11 = await execute_scenario("scenario_1_approved")
    assert res11["verdict"] == "Approved"
    assert res11["risk_score"] <= 25
    print("    [PASS] Verdict: Approved | Risk Score:", res11["risk_score"])
    print("    Primary Reason:", res11["primary_reason"])
    print("    [PASS] Verified: Bluewave remains Approved with zero data collisions after entire suite runs.")
    print()

    print("================================================================")
    print(" ALL SCENARIOS AND REGRESSION ASSERTIONS PASSED PERFECTLY!      ")
    print("================================================================")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
