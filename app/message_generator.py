from typing import Optional, Dict, Any, List
from app.models import VerdictStatus, StageResult, VendorSubmission


def generate_vendor_message(
    submission: VendorSubmission,
    verdict: VerdictStatus,
    primary_reason: str,
    stages: List[StageResult],
    flag_type: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate deterministic, warm, direct, and actionable vendor-facing communication.
    The rules engine decides the content deterministically and explicitly quotes mismatched values.
    """
    contact = submission.contact_name or "Vendor Representative"
    company = submission.legal_company_name or "your company"
    context = context or {}

    if verdict == VerdictStatus.APPROVED:
        notes = []
        for s in stages:
            for n in s.notes:
                if "personal email" in n.lower() or "relationship note" in n.lower() or "cross-border" in n.lower():
                    notes.append(n)
        
        msg = f"Dear {contact},\n\n"
        msg += f"We are pleased to inform you that the vendor onboarding submission for {company} has been verified and Approved.\n\n"
        msg += "Your company profile is now active in our vendor management and payment systems, and you are clear for commercial operations.\n"
        if notes:
            msg += "\nOperational Notes on File:\n"
            for n in notes:
                msg += f"• {n}\n"
        msg += "\nThank you for completing the verification process promptly.\n\nBest regards,\nProcurement & Vendor Operations Team"
        return msg

    if verdict == VerdictStatus.REJECTED:
        if flag_type in ["sanctions_match", "sanctions_hard_match"] or (flag_type and "sanctions" in flag_type) or "sanctions" in primary_reason.lower() or "embargoed" in primary_reason.lower():
            msg = f"Dear {contact},\n\n"
            msg += f"Thank you for submitting your vendor onboarding details for {company}.\n\n"
            msg += "We're unable to proceed with this application. This has been referred to our compliance team.\n\n"
            msg += "Best regards,\nCompliance & Risk Operations Team"
            return msg

        elif flag_type == "duplicate_bank_account" or "duplicate bank" in primary_reason.lower():
            acc_tail = submission.bank_account_number[-4:] if len(submission.bank_account_number) >= 4 else submission.bank_account_number
            msg = f"Dear {contact},\n\n"
            msg += f"Thank you for your onboarding submission for {company}.\n\n"
            msg += f"During our automated compliance checks, our system identified a bank account record conflict regarding the submitted account ending in *{acc_tail}.\n\n"
            msg += "To protect all parties and prevent unauthorized account routing, this submission has been paused and escalated directly to our Compliance & Risk Management team for manual verification.\n\n"
            msg += "A compliance officer will reach out directly to your registered contact email or phone if additional corporate authorization or identity verification is required.\n\n"
            msg += "Best regards,\nCompliance & Risk Operations Team"
            return msg

        elif flag_type == "critical_wrong_company_doc" or "identity document mismatch" in primary_reason.lower():
            critical_mismatches = context.get("critical_doc_mismatches", [])
            msg = f"Dear {contact},\n\n"
            msg += f"Thank you for your onboarding submission for {company}.\n\n"
            msg += "We are unable to approve your application because one or more uploaded supporting documents belong to an entirely different legal entity:\n\n"
            if critical_mismatches:
                for item in critical_mismatches:
                    msg += f"• {item['document']}: Uploaded document is issued to '{item['doc_value']}', which does not match your applicant name '{submission.legal_company_name}'.\n"
            else:
                msg += f"• {primary_reason}\n"
            msg += "\nOfficial corporate and tax certificates must be issued directly to the applicant legal entity. Please ensure you upload the correct certificates registered under your company name and resubmit your application.\n\n"
            msg += "Best regards,\nProcurement Verification Team"
            return msg

        elif flag_type == "tax_country_fraud" or "different country" in primary_reason.lower() or "tax id" in primary_reason.lower():
            detected_country = context.get("tax_detected_country", "another jurisdiction")
            msg = f"Dear {contact},\n\n"
            msg += f"Thank you for submitting onboarding details for {company}.\n\n"
            msg += f"We are unable to approve your application because the submitted Tax ID ({submission.tax_id}) does not match the required national tax format for {submission.country}. "
            msg += f"Our validation checks indicate this tax identifier corresponds to the format used in {detected_country}.\n\n"
            msg += f"Action Required:\n"
            msg += f"• Please confirm your official tax registration number issued by the tax authorities in {submission.country}.\n"
            msg += f"• Submit a corresponding tax certificate issued under the jurisdiction of {submission.country}.\n\n"
            msg += "Please resubmit your application with the corrected tax documentation.\n\nBest regards,\nProcurement Verification Team"
            return msg

        else:
            msg = f"Dear {contact},\n\n"
            msg += f"Thank you for submitting onboarding details for {company}.\n\n"
            msg += f"Unfortunately, we are unable to approve this vendor application due to the following critical issue:\n"
            msg += f"• {primary_reason}\n\n"
            msg += "If you believe this determination was made in error, please contact our vendor support desk.\n\nBest regards,\nProcurement Verification Team"
            return msg

    # verdict == VerdictStatus.PENDING
    if flag_type in ["sanctions_review", "sanctions_moderate_match"] or (flag_type and "sanctions" in flag_type) or "sanctions" in primary_reason.lower():
        msg = f"Dear {contact},\n\n"
        msg += f"Thank you for your onboarding submission for {company}.\n\n"
        msg += "Your application is under additional review. We'll follow up shortly.\n\n"
        msg += "Best regards,\nCompliance & Risk Operations Team"
        return msg

    elif flag_type == "returning_vendor_expired_doc" or "expired" in primary_reason.lower():
        expiry_date = context.get("expired_date", "the stated validity period")
        msg = f"Dear {contact},\n\n"
        msg += f"Thank you for submitting the updated vendor profile for {company}.\n\n"
        msg += f"We appreciate your ongoing partnership. Our records recognize your previously approved vendor profile. "
        msg += f"However, during re-verification, we noticed that your submitted Tax Certificate has an expiration date of {expiry_date}, which has elapsed.\n\n"
        msg += "Action Required (Lightweight Follow-up):\n"
        msg += "• Please upload a copy of your renewed, currently active Tax Certificate.\n\n"
        msg += "Because all other aspects of your profile and banking remain validated, no other documents or full re-application are required. Once the renewed certificate is uploaded, your approval will be renewed immediately.\n\n"
        msg += "Best regards,\nVendor Operations Team"
        return msg

    elif flag_type == "field_mismatch" or "field discrepancy" in primary_reason.lower():
        discrepancies = context.get("field_discrepancies", [])
        msg = f"Dear {contact},\n\n"
        msg += f"Thank you for submitting your onboarding details for {company}.\n\n"
        msg += "During our cross-document verification, our system detected discrepancies between the values entered on the application form and the values stated in your uploaded documents:\n\n"
        if discrepancies:
            for disc in discrepancies:
                msg += f"• {disc['field']}: The application form specified '{disc['form_value']}', but the uploaded {disc['document']} shows '{disc['doc_value']}'.\n"
        else:
            msg += f"• {primary_reason}\n"
        msg += "\nAction Required:\n"
        msg += "• Please review the values listed above and confirm the accurate details, or upload updated document copies that match your application form.\n\n"
        msg += "Once updated, we will resume processing your application promptly.\n\nBest regards,\nVendor Operations Team"
        return msg

    elif flag_type == "name_mismatch" or "bank account holder" in primary_reason.lower() or "name mismatch" in primary_reason.lower():
        bank_holder = context.get("bank_holder_name", submission.bank_account_holder)
        msg = f"Dear {contact},\n\n"
        msg += f"Thank you for submitting your onboarding details for {company}.\n\n"
        msg += f"During our review of your documentation, we identified a variation between your legal company name ('{submission.legal_company_name}') and the account holder name on your bank confirmation letter ('{bank_holder}').\n\n"
        msg += "Action Required:\n"
        msg += "• If your banking operations are managed by a parent entity, subsidiary, or designated treasury partner, please provide a brief relationship explanation in the Relationship Note field (or attach a corporate authorization letter).\n"
        msg += "• Alternatively, if the account should be held directly in the legal company's name, please upload an updated bank confirmation letter in the legal entity's name.\n\n"
        msg += "Once clarified, we will be glad to complete your onboarding.\n\nBest regards,\nVendor Operations Team"
        return msg

    elif flag_type in ["missing_fields", "unreadable_documents"] or "missing" in primary_reason.lower() or "unreadable" in primary_reason.lower():
        issues = context.get("missing_items", [primary_reason])
        msg = f"Dear {contact},\n\n"
        msg += f"Thank you for submitting your onboarding application for {company}.\n\n"
        msg += "We are currently unable to complete verification because several required items are missing or could not be verified:\n\n"
        for item in issues:
            msg += f"• {item}\n"
        msg += "\nPlease update these fields or upload clear, machine-readable PDF copies and resubmit your application.\n\nBest regards,\nVendor Operations Team"
        return msg

    else:
        msg = f"Dear {contact},\n\n"
        msg += f"Thank you for submitting your vendor onboarding application for {company}.\n\n"
        msg += f"Your application is currently pending clarification regarding:\n"
        msg += f"• {primary_reason}\n\n"
        msg += "Please review this item and provide the requested clarification or updated documentation at your earliest convenience.\n\nBest regards,\nVendor Operations Team"
        return msg
