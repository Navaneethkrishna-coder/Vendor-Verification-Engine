import re
import uuid
import string
import difflib
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple, AsyncGenerator

from app.models import (
    VendorSubmission,
    StageResult,
    StageStatus,
    VerdictStatus,
    VerificationResult
)
from app.database import (
    find_bank_account_history,
    find_tax_id_history,
    save_run
)
from app.pdf_parser import (
    extract_text_from_pdf_bytes,
    extract_registration_fields,
    extract_tax_fields,
    extract_bank_fields
)
from app.message_generator import generate_vendor_message


# Legal corporate suffixes to normalize before fuzzy comparison
LEGAL_SUFFIXES = [
    r"\bltd\b", r"\blimited\b", r"\bllc\b", r"\binc\b", r"\bincorporated\b",
    r"\bcorp\b", r"\bcorporation\b", r"\bco\b", r"\bcompany\b", r"\bgmbh\b",
    r"\bag\b", r"\bsa\b", r"\bsas\b", r"\bbv\b", r"\bnv\b", r"\bpvt\b",
    r"\bpvt ltd\b", r"\bprivate limited\b", r"\bplc\b", r"\bllp\b",
    r"\bsdn bhd\b", r"\bholdings\b", r"\bgroup holdings\b", r"\bgroup\b",
    r"\benterprises\b", r"\binternational\b", r"\bpartners\b"
]

# Restricted parties and embargoed jurisdictions for compliance screening (fictional data)
RESTRICTED_PARTY_NAMES = [
    "Talon Sentinel Trading Co",
    "Karim Bashir",
]
EMBARGOED_COUNTRIES = [
    "Freedonia",  # fictional -- avoid using any real country here
]

# Country-specific Tax ID regex patterns
TAX_ID_PATTERNS = {
    "United States": {
        "pattern": r"^\d{2}-\d{7}$",
        "description": "US EIN (NN-NNNNNNN)"
    },
    "United Kingdom": {
        "pattern": r"^(GB)?\s*\d{9}(\d{3})?$",
        "description": "UK VAT (GBNNNNNNNNN)"
    },
    "Germany": {
        "pattern": r"^DE\s*\d{9}$",
        "description": "Germany VAT (DENNNNNNNNN)"
    },
    "India": {
        "pattern": r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1}$",
        "description": "India GSTIN (15-character alphanumeric)"
    },
    "Singapore": {
        "pattern": r"^\d{8,9}[A-Z]$|^[TSR]\d{2}[A-Z]{2}\d{4}[A-Z]$",
        "description": "Singapore UEN"
    },
    "United Arab Emirates": {
        "pattern": r"^100\d{12}$|^\d{15}$",
        "description": "UAE TRN (15 digits)"
    }
}

COUNTRY_ALIASES = {
    "usa": "united states",
    "u.s.a.": "united states",
    "u.s.": "united states",
    "us": "united states",
    "america": "united states",
    "united states of america": "united states",
    "united states": "united states",
    "uk": "united kingdom",
    "u.k.": "united kingdom",
    "great britain": "united kingdom",
    "britain": "united kingdom",
    "england": "united kingdom",
    "united kingdom": "united kingdom",
    "de": "germany",
    "germany": "germany",
    "deutschland": "germany",
    "in": "india",
    "india": "india",
    "bharat": "india",
    "sg": "singapore",
    "singapore": "singapore",
    "uae": "united arab emirates",
    "u.a.e.": "united arab emirates",
    "united arab emirates": "united arab emirates",
    "emirates": "united arab emirates"
}

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "aol.com", "protonmail.com", "mail.com", "zoho.com", "yandex.com"
}


def normalize_name(name: str) -> str:
    """Normalize company name by stripping legal suffixes, punctuation, and extra whitespace."""
    if not name:
        return ""
    cleaned = name.lower()
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    for suffix in LEGAL_SUFFIXES:
        cleaned = re.sub(suffix, " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def calculate_name_similarity(name1: str, name2: str) -> float:
    """Calculate fuzzy string similarity between two names after normalization."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0
    
    seq_ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
    tokens1 = set(n1.split())
    tokens2 = set(n2.split())
    if tokens1 and tokens2:
        intersection = tokens1.intersection(tokens2)
        token_ratio = len(intersection) / max(len(tokens1), len(tokens2))
        return max(seq_ratio, token_ratio)
    
    return seq_ratio


def calculate_sanctions_similarity(name1: str, name2: str) -> float:
    """
    Calculate fuzzy similarity for sanctions screening after normalize_name.
    Reuses the existing normalize_name() function to strip legal suffixes.
    Combines sequence ratio and token overlap to accurately capture moderate
    variation (~75-85%) when key terms differ.
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0
    
    seq_ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
    tokens1 = set(n1.split())
    tokens2 = set(n2.split())
    if tokens1 and tokens2:
        intersection = tokens1.intersection(tokens2)
        token_ratio = len(intersection) / max(len(tokens1), len(tokens2))
        if token_ratio == 1.0:
            return seq_ratio
        return (seq_ratio + token_ratio) / 2.0
    
    return seq_ratio


def normalize_identifier(val: Optional[str]) -> str:
    """Normalize exact identifier codes by removing spaces, dashes, punctuation, and converting to uppercase."""
    if not val:
        return ""
    return re.sub(r"[\s\-\_\.\,\/\#\(\)]", "", str(val)).upper()


def normalize_country(country_str: Optional[str]) -> str:
    """Normalize country names and common abbreviations."""
    if not country_str:
        return ""
    clean = re.sub(r"[^\w\s]", "", str(country_str).strip().lower())
    clean = re.sub(r"\s+", " ", clean)
    return COUNTRY_ALIASES.get(clean, clean)


def detect_tax_id_format_match(tax_id: str) -> Optional[str]:
    """Check if tax_id matches any registered national tax format."""
    clean_tax = tax_id.strip()
    for country, rule in TAX_ID_PATTERNS.items():
        if re.match(rule["pattern"], clean_tax, re.IGNORECASE):
            return country
    return None


def parse_date_safely(date_str: Optional[str]) -> Optional[date]:
    """Safely parse various date string representations."""
    if not date_str:
        return None
    clean_str = date_str.strip()
    formats = [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
        "%Y/%m/%d", "%d.%m.%Y", "%B %d, %Y", "%b %d, %Y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt).date()
        except ValueError:
            continue
    return None


async def run_verification_engine(
    submission: VendorSubmission,
    documents: Dict[str, bytes],
    run_id: Optional[str] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Executes the 8-stage vendor onboarding verification pipeline in exact order.
    Yields events at each stage completion for real-time SSE streaming,
    and yields the final completed VerificationResult.
    """
    if not run_id:
        run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"

    timestamp = datetime.now().isoformat()
    stages: List[StageResult] = []
    accumulated_risk = 0
    context: Dict[str, Any] = {
        "field_discrepancies": [],
        "critical_doc_mismatches": []
    }

    # -------------------------------------------------------------
    # STAGE 1: Sanctions & Restricted-Party Screening
    # -------------------------------------------------------------
    screened_names = [
        ("legal_company_name", submission.legal_company_name),
        ("trading_name", submission.trading_name or ""),
        ("contact_name", submission.contact_name or "")
    ]

    highest_sanctions_sim = 0.0
    top_sanctions_match = None

    for field_key, field_val in screened_names:
        if not field_val or not str(field_val).strip():
            continue
        for r_name in RESTRICTED_PARTY_NAMES:
            sim = calculate_sanctions_similarity(field_val, r_name)
            if sim > highest_sanctions_sim:
                highest_sanctions_sim = sim
                top_sanctions_match = {
                    "field": field_key,
                    "field_label": field_key.replace("_", " ").title(),
                    "value": field_val,
                    "restricted_name": r_name,
                    "similarity": round(sim, 3)
                }

    # Screen country against embargoed list (exact, case-insensitive)
    is_embargoed_country = False
    matched_embargoed_country = None
    clean_sub_country = (submission.country or "").strip().lower()
    for emb_c in EMBARGOED_COUNTRIES:
        if clean_sub_country == emb_c.strip().lower():
            is_embargoed_country = True
            matched_embargoed_country = emb_c
            break

    s1_notes: List[str] = []
    if is_embargoed_country or highest_sanctions_sim >= 0.90:
        s1_status = StageStatus.FAIL
        s1_risk = 100
        s1_flag = "sanctions_hard_match"
        if is_embargoed_country:
            s1_summary = f"CRITICAL: Embargoed jurisdiction match. Declared country '{submission.country}' matches restricted embargo list."
            s1_notes.append(f"Statutory compliance stop: Country '{submission.country}' matches embargoed list '{matched_embargoed_country}'. Overrides all subsequent checks.")
        else:
            pct = highest_sanctions_sim * 100
            s1_summary = f"CRITICAL: Restricted-party hard match ({top_sanctions_match['field_label']} '{top_sanctions_match['value']}' matches '{top_sanctions_match['restricted_name']}' at {pct:.1f}% similarity)."
            s1_notes.append(f"Statutory compliance stop: {top_sanctions_match['field_label']} '{top_sanctions_match['value']}' matches restricted entity '{top_sanctions_match['restricted_name']}' ({pct:.1f}% similarity >= 90%). Overrides all subsequent checks.")
    elif highest_sanctions_sim >= 0.70:
        s1_status = StageStatus.WARNING
        s1_risk = 40
        s1_flag = "sanctions_review"
        pct = highest_sanctions_sim * 100
        s1_summary = f"Restricted-party potential match: {top_sanctions_match['field_label']} '{top_sanctions_match['value']}' shows {pct:.1f}% similarity to '{top_sanctions_match['restricted_name']}'. Requires compliance review."
        s1_notes.append(f"Internal review: {top_sanctions_match['field_label']} '{top_sanctions_match['value']}' flagged against '{top_sanctions_match['restricted_name']}' ({pct:.1f}% similarity, 70-89% tier). Reason: sanctions_review.")
    else:
        s1_status = StageStatus.PASS
        s1_risk = 0
        s1_flag = None
        s1_summary = "Sanctions screening clear. No matches found on restricted entities, individuals, or embargoed countries."
        s1_notes.append("Screened legal company name, trading name, contact name, and country against restricted parties and embargoed jurisdictions. Clean.")

    context["sanctions_hard_match"] = is_embargoed_country or (highest_sanctions_sim >= 0.90)
    context["sanctions_moderate_match"] = (highest_sanctions_sim >= 0.70 and not (is_embargoed_country or highest_sanctions_sim >= 0.90))
    context["sanctions_top_match"] = top_sanctions_match
    context["embargoed_country_match"] = matched_embargoed_country

    stage1 = StageResult(
        stage_number=1,
        stage_name="Sanctions & Restricted-Party Screening",
        status=s1_status,
        summary=s1_summary,
        details={
            "screened_names": [f"{fn}: '{fv}'" for fn, fv in screened_names if fv],
            "highest_similarity": round(highest_sanctions_sim, 3),
            "top_match": top_sanctions_match,
            "is_embargoed_country": is_embargoed_country,
            "matched_embargoed_country": matched_embargoed_country
        },
        risk_points=s1_risk,
        flag_type=s1_flag,
        notes=s1_notes
    )
    stages.append(stage1)
    accumulated_risk += s1_risk
    yield {"event": "stage_update", "stage": stage1.model_dump(), "progress": 12}

    # -------------------------------------------------------------
    # STAGE 2: Intake & Schema Validation
    # -------------------------------------------------------------
    missing_fields = []
    invalid_format_fields = []
    
    required_fields = [
        ("legal_company_name", submission.legal_company_name),
        ("country", submission.country),
        ("address", submission.address),
        ("contact_name", submission.contact_name),
        ("contact_email", submission.contact_email),
        ("contact_phone", submission.contact_phone),
        ("registration_number", submission.registration_number),
        ("tax_id", submission.tax_id),
        ("bank_name", submission.bank_name),
        ("bank_account_holder", submission.bank_account_holder),
        ("bank_account_number", submission.bank_account_number),
    ]

    for fname, fval in required_fields:
        if not fval or not str(fval).strip():
            missing_fields.append(fname.replace("_", " ").title())

    if submission.contact_email:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", submission.contact_email.strip()):
            invalid_format_fields.append("Contact Email (invalid format)")
            
    if submission.contact_phone:
        if not re.match(r"^[+\d\s\-\(\)\.]{7,25}$", submission.contact_phone.strip()):
            invalid_format_fields.append("Contact Phone (invalid format)")

    if missing_fields or invalid_format_fields:
        issues = missing_fields + invalid_format_fields
        s2_status = StageStatus.FAIL
        s2_summary = f"Validation failed: {len(issues)} missing or invalid fields."
        s2_risk = 40
        s2_flag = "missing_fields"
        context["missing_items"] = [f"Field error: {item}" for item in issues]
    else:
        s2_status = StageStatus.PASS
        s2_summary = "All required submission fields are present and well-formed."
        s2_risk = 0
        s2_flag = None

    stage2 = StageResult(
        stage_number=2,
        stage_name="Intake & Schema Validation",
        status=s2_status,
        summary=s2_summary,
        details={
            "missing_fields": missing_fields,
            "invalid_format_fields": invalid_format_fields,
            "fields_checked": len(required_fields)
        },
        risk_points=s2_risk,
        flag_type=s2_flag,
        notes=[] if s2_status == StageStatus.PASS else [f"Issues identified: {', '.join(issues)}"]
    )
    stages.append(stage2)
    accumulated_risk += s2_risk
    yield {"event": "stage_update", "stage": stage2.model_dump(), "progress": 25}

    # -------------------------------------------------------------
    # STAGE 3: Document Validation
    # -------------------------------------------------------------
    doc_keys = ["registration_certificate", "tax_certificate", "bank_letter"]
    doc_labels = {
        "registration_certificate": "Registration Certificate",
        "tax_certificate": "Tax Certificate",
        "bank_letter": "Bank Confirmation Letter"
    }
    
    extracted_raw_texts: Dict[str, str] = {}
    unreadable_docs: List[str] = []
    doc_details: Dict[str, Any] = {}

    for d_key in doc_keys:
        pdf_bytes = documents.get(d_key, b"")
        if not pdf_bytes:
            unreadable_docs.append(f"{doc_labels[d_key]} (missing file)")
            doc_details[d_key] = {"status": "missing", "text_length": 0}
            continue
        
        text = extract_text_from_pdf_bytes(pdf_bytes)
        if not text or len(text.strip()) == 0:
            unreadable_docs.append(f"{doc_labels[d_key]} (empty or unextractable text)")
            doc_details[d_key] = {"status": "unreadable", "text_length": 0}
        else:
            extracted_raw_texts[d_key] = text
            doc_details[d_key] = {"status": "valid", "text_length": len(text), "preview": text[:120] + "..."}

    if unreadable_docs:
        s3_status = StageStatus.FAIL
        s3_summary = f"Document validation failed: {len(unreadable_docs)} document(s) missing or unreadable."
        s3_risk = 40
        s3_flag = "unreadable_documents"
        if "missing_items" not in context:
            context["missing_items"] = []
        context["missing_items"].extend(unreadable_docs)
    else:
        s3_status = StageStatus.PASS
        s3_summary = "All 3 required PDF documents are present and text is extractable."
        s3_risk = 0
        s3_flag = None

    stage3 = StageResult(
        stage_number=3,
        stage_name="Document Validation",
        status=s3_status,
        summary=s3_summary,
        details={
            "documents": doc_details,
            "unreadable_docs": unreadable_docs
        },
        risk_points=s3_risk,
        flag_type=s3_flag,
        notes=[] if s3_status == StageStatus.PASS else [f"Document errors: {', '.join(unreadable_docs)}"]
    )
    stages.append(stage3)
    accumulated_risk += s3_risk
    yield {"event": "stage_update", "stage": stage3.model_dump(), "progress": 37}

    # -------------------------------------------------------------
    # STAGE 4: Field Extraction from Documents
    # -------------------------------------------------------------
    reg_fields = extract_registration_fields(extracted_raw_texts.get("registration_certificate", ""))
    tax_fields = extract_tax_fields(extracted_raw_texts.get("tax_certificate", ""))
    bank_fields = extract_bank_fields(extracted_raw_texts.get("bank_letter", ""))

    extraction_summary_items = []
    if reg_fields.get("company_name"):
        extraction_summary_items.append(f"Reg Name: '{reg_fields['company_name']}'")
    if tax_fields.get("tax_id"):
        extraction_summary_items.append(f"Tax ID: '{tax_fields['tax_id']}'")
    if bank_fields.get("account_holder"):
        extraction_summary_items.append(f"Bank Holder: '{bank_fields['account_holder']}'")

    missing_extractions = []
    if not reg_fields.get("company_name"):
        missing_extractions.append("Registration Certificate Company Name")
    if not tax_fields.get("tax_id"):
        missing_extractions.append("Tax Certificate Tax ID")
    if not bank_fields.get("account_holder"):
        missing_extractions.append("Bank Letter Account Holder")

    if missing_extractions:
        s4_status = StageStatus.WARNING
        s4_summary = f"Partial extraction: Missing {len(missing_extractions)} critical label(s)."
        s4_risk = 15
        s4_flag = "partial_extraction"
    else:
        s4_status = StageStatus.PASS
        s4_summary = f"Successfully parsed label:value pairs across all 3 documents ({', '.join(extraction_summary_items)})."
        s4_risk = 0
        s4_flag = None

    stage4 = StageResult(
        stage_number=4,
        stage_name="Field Extraction from Documents",
        status=s4_status,
        summary=s4_summary,
        details={
            "registration_certificate": {
                "company_name": reg_fields.get("company_name"),
                "registration_number": reg_fields.get("registration_number"),
                "country": reg_fields.get("country"),
            },
            "tax_certificate": {
                "taxpayer_name": tax_fields.get("taxpayer_name"),
                "tax_id": tax_fields.get("tax_id"),
                "country": tax_fields.get("country"),
                "valid_until": tax_fields.get("valid_until"),
            },
            "bank_letter": {
                "account_holder": bank_fields.get("account_holder"),
                "bank_name": bank_fields.get("bank_name"),
                "account_number": bank_fields.get("account_number"),
                "swift_bic": bank_fields.get("swift_bic"),
            }
        },
        risk_points=s4_risk,
        flag_type=s4_flag,
        notes=[] if not missing_extractions else [f"Could not extract: {', '.join(missing_extractions)}"]
    )
    stages.append(stage4)
    accumulated_risk += s4_risk
    yield {"event": "stage_update", "stage": stage4.model_dump(), "progress": 50}

    # -------------------------------------------------------------
    # STAGE 4: Comprehensive Cross-Document Consistency Check
    # -------------------------------------------------------------
    # Compare EVERY field extracted from each document against form fields:
    # 1. Reg Cert: Company Name, Registration Number, Country
    # 2. Tax Cert: Company Name / Taxpayer Name, Tax ID, Country
    # 3. Bank Letter: Account Holder, Bank Name, Account Number, SWIFT/BIC

    s4_notes: List[str] = []
    field_discrepancies: List[Dict[str, Any]] = []
    critical_wrong_company_docs: List[Dict[str, Any]] = []
    has_relationship_note = bool(submission.relationship_note and submission.relationship_note.strip())

    # Comparison 1: Registration Certificate Company Name (Fuzzy)
    doc_reg_name = reg_fields.get("company_name")
    if doc_reg_name:
        sim_reg_name = calculate_name_similarity(submission.legal_company_name, doc_reg_name)
        if sim_reg_name < 0.55:
            # Critical: Issued to completely different company!
            critical_wrong_company_docs.append({
                "document": "Registration Certificate",
                "field": "Company Name",
                "form_value": submission.legal_company_name,
                "doc_value": doc_reg_name,
                "similarity": round(sim_reg_name, 3)
            })
            s4_notes.append(f"CRITICAL: Registration certificate belongs to a completely different company '{doc_reg_name}' ({sim_reg_name*100:.1f}% similarity vs '{submission.legal_company_name}')")
        elif sim_reg_name < 0.85:
            field_discrepancies.append({
                "document": "Registration Certificate",
                "field": "Company Name",
                "form_value": submission.legal_company_name,
                "doc_value": doc_reg_name,
                "type": "name_variation"
            })
            s4_notes.append(f"Registration certificate name variation: form has '{submission.legal_company_name}', document shows '{doc_reg_name}' ({sim_reg_name*100:.1f}%)")

    # Comparison 2: Registration Certificate Registration Number (Exact Normalized Match)
    doc_reg_num = reg_fields.get("registration_number")
    if doc_reg_num:
        norm_form_reg = normalize_identifier(submission.registration_number)
        norm_doc_reg = normalize_identifier(doc_reg_num)
        if norm_form_reg != norm_doc_reg:
            field_discrepancies.append({
                "document": "Registration Certificate",
                "field": "Company Registration Number",
                "form_value": submission.registration_number,
                "doc_value": doc_reg_num,
                "type": "exact_mismatch"
            })
            s4_notes.append(f"Registration Number mismatch: form has '{submission.registration_number}', document shows '{doc_reg_num}'")

    # Comparison 3: Registration Certificate Country (Normalized Match)
    doc_reg_country = reg_fields.get("country")
    if doc_reg_country:
        norm_form_c = normalize_country(submission.country)
        norm_doc_c = normalize_country(doc_reg_country)
        if norm_form_c != norm_doc_c:
            field_discrepancies.append({
                "document": "Registration Certificate",
                "field": "Country of Incorporation",
                "form_value": submission.country,
                "doc_value": doc_reg_country,
                "type": "exact_mismatch"
            })
            s4_notes.append(f"Country mismatch on registration certificate: form has '{submission.country}', document shows '{doc_reg_country}'")

    # Comparison 4: Tax Certificate Company Name / Taxpayer Name (Fuzzy)
    doc_tax_name = tax_fields.get("taxpayer_name")
    if doc_tax_name:
        sim_tax_name = calculate_name_similarity(submission.legal_company_name, doc_tax_name)
        if sim_tax_name < 0.55:
            # Critical: Issued to completely different company!
            critical_wrong_company_docs.append({
                "document": "Tax Certificate",
                "field": "Taxpayer Name",
                "form_value": submission.legal_company_name,
                "doc_value": doc_tax_name,
                "similarity": round(sim_tax_name, 3)
            })
            s4_notes.append(f"CRITICAL: Tax certificate issued to a completely different company '{doc_tax_name}' ({sim_tax_name*100:.1f}% similarity vs '{submission.legal_company_name}')")
        elif sim_tax_name < 0.85:
            field_discrepancies.append({
                "document": "Tax Certificate",
                "field": "Taxpayer Name",
                "form_value": submission.legal_company_name,
                "doc_value": doc_tax_name,
                "type": "name_variation"
            })
            s4_notes.append(f"Tax certificate name variation: form has '{submission.legal_company_name}', document shows '{doc_tax_name}' ({sim_tax_name*100:.1f}%)")

    # Comparison 5: Tax Certificate Tax ID (Exact Normalized Match)
    doc_tax_id = tax_fields.get("tax_id")
    if doc_tax_id:
        norm_form_tax = normalize_identifier(submission.tax_id)
        norm_doc_tax = normalize_identifier(doc_tax_id)
        if norm_form_tax != norm_doc_tax:
            field_discrepancies.append({
                "document": "Tax Certificate",
                "field": "Tax ID",
                "form_value": submission.tax_id,
                "doc_value": doc_tax_id,
                "type": "exact_mismatch"
            })
            s4_notes.append(f"Tax ID mismatch: form has '{submission.tax_id}', document shows '{doc_tax_id}'")

    # Comparison 6: Tax Certificate Country (Normalized Match)
    doc_tax_country = tax_fields.get("country")
    if doc_tax_country:
        norm_form_tc = normalize_country(submission.country)
        norm_doc_tc = normalize_country(doc_tax_country)
        if norm_form_tc != norm_doc_tc:
            field_discrepancies.append({
                "document": "Tax Certificate",
                "field": "Tax Jurisdiction Country",
                "form_value": submission.country,
                "doc_value": doc_tax_country,
                "type": "exact_mismatch"
            })
            s4_notes.append(f"Country mismatch on tax certificate: form has '{submission.country}', document shows '{doc_tax_country}'")

    # Comparison 7: Bank Letter Account Holder Name (Fuzzy with Relationship Note logic)
    bank_holder_name = bank_fields.get("account_holder") or submission.bank_account_holder or ""
    context["bank_holder_name"] = bank_holder_name
    sim_legal_bank = calculate_name_similarity(submission.legal_company_name, bank_holder_name)
    sim_trading_bank = calculate_name_similarity(submission.trading_name, bank_holder_name) if submission.trading_name else 0.0
    best_bank_similarity = max(sim_legal_bank, sim_trading_bank)

    bank_holder_mismatch = False
    bank_holder_explained = False

    if best_bank_similarity >= 0.92:
        s4_notes.append(f"Bank account holder '{bank_holder_name}' matches company name ({best_bank_similarity*100:.1f}%)")
    elif 0.55 <= best_bank_similarity < 0.92:
        if has_relationship_note:
            bank_holder_explained = True
            s4_notes.append(f"Moderate bank name variation ({best_bank_similarity*100:.1f}%), cleared by relationship note: \"{submission.relationship_note}\"")
        else:
            bank_holder_mismatch = True
            field_discrepancies.append({
                "document": "Bank Confirmation Letter",
                "field": "Bank Account Holder Name",
                "form_value": submission.legal_company_name,
                "doc_value": bank_holder_name,
                "type": "bank_holder_mismatch"
            })
            s4_notes.append(f"Bank account holder name mismatch ({best_bank_similarity*100:.1f}%): held by '{bank_holder_name}' (No explanation note)")
    else:
        # Severe bank holder mismatch (< 55%)
        if has_relationship_note:
            bank_holder_explained = True
            s4_notes.append(f"Separate bank holder '{bank_holder_name}' ({best_bank_similarity*100:.1f}%), relationship note recorded: \"{submission.relationship_note}\"")
        else:
            bank_holder_mismatch = True
            field_discrepancies.append({
                "document": "Bank Confirmation Letter",
                "field": "Bank Account Holder Name",
                "form_value": submission.legal_company_name,
                "doc_value": bank_holder_name,
                "type": "bank_holder_mismatch"
            })
            s4_notes.append(f"Severe bank holder mismatch ({best_bank_similarity*100:.1f}%): held by '{bank_holder_name}' without relationship note")

    # Comparison 8: Bank Letter Account Number (Exact Normalized Match)
    doc_bank_acc = bank_fields.get("account_number")
    if doc_bank_acc:
        norm_form_acc = normalize_identifier(submission.bank_account_number)
        norm_doc_acc = normalize_identifier(doc_bank_acc)
        if norm_form_acc != norm_doc_acc:
            field_discrepancies.append({
                "document": "Bank Confirmation Letter",
                "field": "Bank Account Number",
                "form_value": submission.bank_account_number,
                "doc_value": doc_bank_acc,
                "type": "exact_mismatch"
            })
            s4_notes.append(f"Bank Account Number mismatch: form has '{submission.bank_account_number}', document shows '{doc_bank_acc}'")

    # Comparison 9: Bank Letter Bank Name (Fuzzy Match)
    doc_bank_name = bank_fields.get("bank_name")
    if doc_bank_name and submission.bank_name:
        sim_bname = calculate_name_similarity(submission.bank_name, doc_bank_name)
        if sim_bname < 0.70:
            field_discrepancies.append({
                "document": "Bank Confirmation Letter",
                "field": "Bank Name",
                "form_value": submission.bank_name,
                "doc_value": doc_bank_name,
                "type": "exact_mismatch"
            })
            s4_notes.append(f"Bank name variation: form has '{submission.bank_name}', document shows '{doc_bank_name}' ({sim_bname*100:.1f}%)")

    # Comparison 10: Bank Letter SWIFT/BIC (Exact Normalized Match if present)
    doc_swift = bank_fields.get("swift_bic")
    if doc_swift and submission.swift_bic:
        norm_form_swift = normalize_identifier(submission.swift_bic)
        norm_doc_swift = normalize_identifier(doc_swift)
        if norm_form_swift != norm_doc_swift:
            field_discrepancies.append({
                "document": "Bank Confirmation Letter",
                "field": "SWIFT/BIC",
                "form_value": submission.swift_bic,
                "doc_value": doc_swift,
                "type": "exact_mismatch"
            })
            s4_notes.append(f"SWIFT/BIC mismatch: form has '{submission.swift_bic}', document shows '{doc_swift}'")

    context["field_discrepancies"] = field_discrepancies
    context["critical_doc_mismatches"] = critical_wrong_company_docs

    # Determine Stage 5 status & risk points
    if critical_wrong_company_docs:
        s5_status = StageStatus.FAIL
        s5_summary = f"CRITICAL: Uploaded identity document(s) issued to a completely different company ({critical_wrong_company_docs[0]['document']}: '{critical_wrong_company_docs[0]['doc_value']}')."
        s5_risk = 85
        s5_flag = "critical_wrong_company_doc"
    elif field_discrepancies:
        s5_status = StageStatus.WARNING
        s5_summary = f"Field consistency check flagged {len(field_discrepancies)} discrepancy item(s) between form and documents."
        s5_risk = 45
        s5_flag = "field_mismatch"
    elif bank_holder_explained:
        s5_status = StageStatus.INFO
        s5_summary = f"All fields match. Bank account name variation cleared by vendor relationship explanation note."
        s5_risk = 10
        s5_flag = "name_mismatch_explained"
    else:
        s5_status = StageStatus.PASS
        s5_summary = "All 10 extracted document fields match the submitted form values exactly."
        s5_risk = 0
        s5_flag = None

    stage5 = StageResult(
        stage_number=5,
        stage_name="Cross-Document Consistency Check",
        status=s5_status,
        summary=s5_summary,
        details={
            "field_discrepancies_count": len(field_discrepancies),
            "critical_doc_mismatches_count": len(critical_wrong_company_docs),
            "discrepancies": field_discrepancies,
            "critical_mismatches": critical_wrong_company_docs,
            "bank_holder_similarity": round(best_bank_similarity, 3),
            "relationship_note": submission.relationship_note
        },
        risk_points=s5_risk,
        flag_type=s5_flag,
        notes=s4_notes
    )
    stages.append(stage5)
    accumulated_risk += s5_risk
    yield {"event": "stage_update", "stage": stage5.model_dump(), "progress": 62}

    # -------------------------------------------------------------
    # STAGE 6: Tax ID & Bank Country Consistency
    # -------------------------------------------------------------
    s6_notes: List[str] = []
    s6_risk = 0
    s6_flag = None

    tax_id_to_check = submission.tax_id.strip()
    declared_country = submission.country.strip()

    country_rule = TAX_ID_PATTERNS.get(declared_country)
    tax_format_valid_for_declared = False
    
    if country_rule:
        if re.match(country_rule["pattern"], tax_id_to_check, re.IGNORECASE):
            tax_format_valid_for_declared = True
    else:
        tax_format_valid_for_declared = bool(re.match(r"^[A-Za-z0-9\-\s]{5,25}$", tax_id_to_check))

    detected_other_country = detect_tax_id_format_match(tax_id_to_check)
    
    if not tax_format_valid_for_declared and detected_other_country and detected_other_country != declared_country:
        # HARD, PROVABLE INCONSISTENCY / FRAUD SIGNAL
        s6_status = StageStatus.FAIL
        s6_summary = f"Critical Tax ID anomaly: Declared '{declared_country}', but Tax ID '{tax_id_to_check}' matches format for '{detected_other_country}'."
        s6_notes.append(f"Hard inconsistency: Pattern matches {TAX_ID_PATTERNS[detected_other_country]['description']} rather than {declared_country}")
        s6_risk = 85
        s6_flag = "tax_country_fraud"
        context["tax_detected_country"] = detected_other_country
    elif not tax_format_valid_for_declared:
        s6_status = StageStatus.WARNING
        s6_summary = f"Tax ID '{tax_id_to_check}' does not match standard pattern for {declared_country}."
        s6_notes.append(f"Expected format pattern for {declared_country}")
        s6_risk = 25
        s6_flag = "tax_format_irregular"
    else:
        s6_status = StageStatus.PASS
        s6_summary = f"Tax ID format matches expected standard for {declared_country}."

    # Soft bank country check (IBAN prefix or SWIFT country code)
    bank_acc = submission.bank_account_number.strip().upper().replace(" ", "")
    if len(bank_acc) >= 2 and bank_acc[:2].isalpha():
        iban_country_code = bank_acc[:2]
        iso_map = {"GB": "United Kingdom", "DE": "Germany", "US": "United States", "IN": "India", "SG": "Singapore", "AE": "United Arab Emirates"}
        expected_iso = {v: k for k, v in iso_map.items()}.get(declared_country)
        if expected_iso and iban_country_code != expected_iso:
            s6_notes.append(f"Cross-border banking note: IBAN country prefix '{iban_country_code}' differs from declared country '{declared_country}' (non-blocking)")
            s6_risk += 5

    stage6 = StageResult(
        stage_number=6,
        stage_name="Tax ID & Bank Country Consistency",
        status=s6_status,
        summary=s6_summary,
        details={
            "tax_id": tax_id_to_check,
            "declared_country": declared_country,
            "tax_format_valid_for_declared": tax_format_valid_for_declared,
            "detected_foreign_country": detected_other_country if detected_other_country != declared_country else None
        },
        risk_points=s6_risk,
        flag_type=s6_flag,
        notes=s6_notes
    )
    stages.append(stage6)
    accumulated_risk += s6_risk
    yield {"event": "stage_update", "stage": stage6.model_dump(), "progress": 75}

    # -------------------------------------------------------------
    # STAGE 7: Risk & Vendor History Check
    # -------------------------------------------------------------
    s7_notes: List[str] = []
    s7_risk = 0
    s7_flag = None
    is_duplicate_bank_reuse = False
    is_returning_vendor = False
    is_tax_cert_expired = False
    expired_date_str = ""

    # 1. Query duplicate bank account history in vendor ledger
    bank_history = find_bank_account_history(submission.bank_account_number)
    for rec in bank_history:
        if rec.get("verdict", "").upper() == "REJECTED":
            continue
        sim = calculate_name_similarity(submission.legal_company_name, rec["company_name"])
        if sim < 0.85:
            is_duplicate_bank_reuse = True
            conflict_company = rec["company_name"]
            s7_notes.append(f"CRITICAL FRAUD SIGNAL: Bank account {submission.bank_account_number} is already on file for '{conflict_company}' (Run: {rec['run_id']})")
            context["duplicate_bank_conflict_company"] = conflict_company
            break

    # 2. Query returning vendor history by tax_id
    tax_history = find_tax_id_history(submission.tax_id)
    approved_past_records = [r for r in tax_history if r["verdict"] == VerdictStatus.APPROVED.value]
    if approved_past_records:
        is_returning_vendor = True
        s7_notes.append(f"Recognized Returning Vendor: Prior approval on file (Run: {approved_past_records[0]['run_id']})")

    # 3. Check tax cert expiration date
    valid_until_str = tax_fields.get("valid_until")
    if valid_until_str:
        parsed_valid_until = parse_date_safely(valid_until_str)
        if parsed_valid_until:
            today_date = date.today()
            if parsed_valid_until < today_date:
                is_tax_cert_expired = True
                expired_date_str = valid_until_str
                context["expired_date"] = valid_until_str
                s7_notes.append(f"Tax certificate expired on {valid_until_str} (Prior to today {today_date.isoformat()})")

    # 4. Soft signal: Personal/free email domain
    email_domain = submission.contact_email.split("@")[-1].lower() if "@" in submission.contact_email else ""
    if email_domain in FREE_EMAIL_DOMAINS:
        s7_notes.append(f"Soft signal: Personal/free email domain detected (@{email_domain}). Non-blocking.")
        s7_risk += 10

    if is_duplicate_bank_reuse:
        s7_status = StageStatus.FAIL
        s7_summary = f"CRITICAL: Bank account reuse detected across different legal entities ('{conflict_company}')."
        s7_risk = 100
        s7_flag = "duplicate_bank_account"
    elif is_returning_vendor and is_tax_cert_expired:
        s7_status = StageStatus.WARNING
        s7_summary = f"Returning vendor verified on file; submitted tax certificate expired on {expired_date_str}."
        s7_risk = 25
        s7_flag = "returning_vendor_expired_doc"
    elif is_returning_vendor:
        s7_status = StageStatus.PASS
        s7_summary = "Returning vendor verified with prior clean approval in vendor ledger."
    else:
        s7_status = StageStatus.PASS
        s7_summary = "No conflicting bank records or adverse history found in vendor ledger."

    stage7 = StageResult(
        stage_number=7,
        stage_name="Risk & Vendor History Check",
        status=s7_status,
        summary=s7_summary,
        details={
            "is_duplicate_bank_reuse": is_duplicate_bank_reuse,
            "is_returning_vendor": is_returning_vendor,
            "is_tax_cert_expired": is_tax_cert_expired,
            "email_domain": email_domain,
            "prior_tax_records_count": len(tax_history),
            "bank_records_count": len(bank_history)
        },
        risk_points=s7_risk,
        flag_type=s7_flag,
        notes=s7_notes
    )
    stages.append(stage7)
    accumulated_risk += s7_risk
    yield {"event": "stage_update", "stage": stage7.model_dump(), "progress": 87}

    # -------------------------------------------------------------
    # STAGE 8: Decision Priority & Risk Synthesis
    # -------------------------------------------------------------
    # ORDER OF PRECEDENCE (Strict Decision Priority Order):
    # 1. Sanctions hard match (name >= 90% OR embargoed country) -> Rejected (Checked FIRST, legal/compliance stop)
    # 2. Duplicate bank account reuse under a different company name -> Rejected (Escalate to compliance)
    # 3. Tax ID format provably matches a different country than declared -> Rejected
    # 4. Registration or Tax cert issued to completely different company (< 55% similarity) -> Rejected
    # 5. Sanctions moderate match (name 70–89%) -> Pending (Internal reason: sanctions_review)
    # 6. Missing required fields or unreadable documents -> Pending (specific, fixable)
    # 7. Returning vendor with single expired document -> Pending (Lightweight)
    # 8. Any other name or field mismatch -> Pending
    # 9. Only soft, non-blocking signals remain -> Approved (with notes)
    # 10. Nothing flagged -> Approved

    verdict: VerdictStatus
    primary_reason: str
    decision_flag: Optional[str] = None
    reason_code: Optional[str] = None
    requires_escalation = False

    if context.get("sanctions_hard_match"):
        # Priority 1: Sanctions hard match (Statutory legal stop - overrides all checks)
        verdict = VerdictStatus.REJECTED
        requires_escalation = True
        accumulated_risk = 100
        decision_flag = "sanctions_match"
        reason_code = "sanctions_match"
        if context.get("embargoed_country_match"):
            primary_reason = f"Restricted Jurisdiction Violation: Declared country '{submission.country}' matches embargoed jurisdiction list ('{context['embargoed_country_match']}'). Statutory compliance requirement: Overrode all subsequent checks."
        else:
            tm = context.get("sanctions_top_match") or {}
            primary_reason = f"Restricted Party Hard Match: {tm.get('field_label', 'Company Name')} '{tm.get('value', submission.legal_company_name)}' matched restricted entity '{tm.get('restricted_name')}' ({tm.get('similarity', 1.0)*100:.1f}% similarity). Statutory compliance requirement: Overrode all subsequent checks."

    elif is_duplicate_bank_reuse:
        # Priority 2: Duplicate bank account reuse
        verdict = VerdictStatus.REJECTED
        conflict_co = context.get("duplicate_bank_conflict_company", "another entity")
        primary_reason = f"Critical Fraud Signal: Bank account number {submission.bank_account_number} is already registered to a different entity ('{conflict_co}'). Escalated for manual compliance investigation."
        decision_flag = "duplicate_bank_account"
        reason_code = "duplicate_bank_account"
        requires_escalation = True
        accumulated_risk = 100

    elif stage6.flag_type == "tax_country_fraud":
        # Priority 3: Tax ID country format fraud
        verdict = VerdictStatus.REJECTED
        detected_c = context.get("tax_detected_country", "another country")
        primary_reason = f"Hard Inconsistency: Declared country '{submission.country}' conflicts with Tax ID '{submission.tax_id}', which positively matches {detected_c} tax formatting rules."
        decision_flag = "tax_country_fraud"
        reason_code = "tax_country_fraud"
        accumulated_risk = max(accumulated_risk, 85)

    elif critical_wrong_company_docs:
        # Priority 4: Uploaded registration/tax cert belongs to completely different company
        verdict = VerdictStatus.REJECTED
        top_mismatch = critical_wrong_company_docs[0]
        primary_reason = f"Identity Document Mismatch: Uploaded {top_mismatch['document']} is issued to '{top_mismatch['doc_value']}', which does not match applicant legal name '{submission.legal_company_name}'."
        decision_flag = "critical_wrong_company_doc"
        reason_code = "critical_wrong_company_doc"
        accumulated_risk = max(accumulated_risk, 85)

    elif context.get("sanctions_moderate_match"):
        # Priority 5: Sanctions moderate match (name 70-89%) -> Pending (sanctions_review)
        verdict = VerdictStatus.PENDING
        decision_flag = "sanctions_review"
        reason_code = "sanctions_review"
        tm = context.get("sanctions_top_match") or {}
        primary_reason = f"Sanctions Review Required: {tm.get('field_label', 'Company Name')} '{tm.get('value', submission.legal_company_name)}' flagged against restricted party '{tm.get('restricted_name')}' with {tm.get('similarity', 0.8)*100:.1f}% similarity. Referred for internal compliance review."
        accumulated_risk = max(accumulated_risk, 40)

    elif stage2.status == StageStatus.FAIL or stage3.status == StageStatus.FAIL:
        # Priority 6: Missing fields or unreadable documents -> Fixable Pending
        verdict = VerdictStatus.PENDING
        missing_list = context.get("missing_items", ["Missing required fields or unreadable documents"])
        primary_reason = f"Incomplete submission: {'; '.join(missing_list[:3])}"
        decision_flag = "missing_fields"
        reason_code = "missing_fields"
        accumulated_risk = max(accumulated_risk, 40)

    elif is_returning_vendor and is_tax_cert_expired:
        # Priority 7: Returning vendor with expired document -> Lightweight Pending
        verdict = VerdictStatus.PENDING
        primary_reason = f"Returning approved vendor: Submitted tax certificate expired on {expired_date_str}. Please provide a renewed tax certificate."
        decision_flag = "returning_vendor_expired_doc"
        reason_code = "returning_vendor_expired_doc"
        accumulated_risk = max(accumulated_risk, 25)

    elif is_tax_cert_expired:
        # Expired tax certificate on a first-time submission -> Pending
        verdict = VerdictStatus.PENDING
        primary_reason = f"The submitted tax certificate expired on {expired_date_str}. A valid, unexpired tax certificate is required."
        decision_flag = "expired_tax_certificate"
        reason_code = "expired_tax_certificate"
        accumulated_risk = max(accumulated_risk, 40)

    elif field_discrepancies:
        # Priority 8: Form vs Document field mismatches
        verdict = VerdictStatus.PENDING
        disc = field_discrepancies[0]
        if disc.get("type") == "bank_holder_mismatch":
            primary_reason = f"Bank account holder name mismatch: Account is held by '{disc['doc_value']}' rather than '{submission.legal_company_name}', and no relationship explanation note was provided."
            decision_flag = "name_mismatch"
            reason_code = "name_mismatch"
        else:
            primary_reason = f"Field Discrepancy: {disc['field']} on form ('{disc['form_value']}') does not match {disc['document']} ('{disc['doc_value']}')."
            decision_flag = "field_mismatch"
            reason_code = "field_mismatch"
        accumulated_risk = max(accumulated_risk, 45)

    else:
        # Priorities 9 & 10: Approved (with notes if soft signals exist)
        verdict = VerdictStatus.APPROVED
        soft_signals = []
        if stage5.flag_type == "name_mismatch_explained":
            soft_signals.append("Bank name variation supported by vendor relationship note")
        if email_domain in FREE_EMAIL_DOMAINS:
            soft_signals.append("Personal email domain on file")
        for s in stages:
            for n in s.notes:
                if "cross-border" in n.lower():
                    soft_signals.append("Cross-border banking note")

        if soft_signals:
            primary_reason = f"Submission approved with informational notes: {', '.join(soft_signals)}."
            decision_flag = "soft_signals_noted"
            reason_code = "soft_signals_noted"
        else:
            primary_reason = "All identity, cross-document fields, tax formatting, and ledger history checks fully verified."
            decision_flag = "all_clean"
            reason_code = "all_clean"
        accumulated_risk = min(accumulated_risk, 25)

    # Clamp total risk score to 0 - 100
    final_risk_score = min(100, max(0, accumulated_risk))

    stage8 = StageResult(
        stage_number=8,
        stage_name="Decision Priority & Risk Synthesis",
        status=StageStatus.PASS if verdict == VerdictStatus.APPROVED else (StageStatus.WARNING if verdict == VerdictStatus.PENDING else StageStatus.FAIL),
        summary=f"Final Verdict: {verdict.value} (Risk Score: {final_risk_score}/100). {primary_reason}",
        details={
            "verdict": verdict.value,
            "risk_score": final_risk_score,
            "primary_reason": primary_reason,
            "decision_flag": decision_flag,
            "reason_code": reason_code,
            "requires_escalation": requires_escalation
        },
        risk_points=0,
        flag_type=decision_flag,
        notes=[f"Verdict: {verdict.value}", f"Primary Rule Applied: {decision_flag or 'All Clean'}", f"Reason Code: {reason_code or 'all_clean'}"]
    )
    stages.append(stage8)

    # Generate vendor-facing communication
    vendor_msg = generate_vendor_message(
        submission=submission,
        verdict=verdict,
        primary_reason=primary_reason,
        stages=stages,
        flag_type=decision_flag,
        context=context
    )

    result = VerificationResult(
        run_id=run_id,
        timestamp=timestamp,
        submission=submission,
        verdict=verdict,
        risk_score=final_risk_score,
        primary_reason=primary_reason,
        stages=stages,
        vendor_message=vendor_msg,
        is_returning_vendor=is_returning_vendor,
        requires_escalation=requires_escalation,
        reason_code=reason_code
    )

    save_run(result)

    yield {"event": "stage_update", "stage": stage8.model_dump(), "progress": 100}
    yield {"event": "complete", "result": result.model_dump()}
