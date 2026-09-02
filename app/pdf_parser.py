import io
import re
from typing import Dict, Any, Optional
from pypdf import PdfReader


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract raw text from PDF binary data using pypdf."""
    if not pdf_bytes or len(pdf_bytes) == 0:
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        extracted_pages = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            extracted_pages.append(page_text)
        return "\n".join(extracted_pages).strip()
    except Exception as e:
        return ""


def parse_key_value_lines(text: str) -> Dict[str, str]:
    """
    Transparently parse key-value pairs from text lines matching 'Label: value'
    or 'Label:' followed by value on next line.
    Returns a dictionary of normalized lowercase keys -> stripped string values.
    """
    kv_map: Dict[str, str] = {}
    if not text:
        return kv_map

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Match "Key : Value" on the same line
        match_same_line = re.match(r"^([A-Za-z0-9\s\/\-_#\(\)]+?)\s*[:：]\s*(.+)$", line)
        if match_same_line:
            raw_key = match_same_line.group(1).strip()
            raw_val = match_same_line.group(2).strip()
            norm_key = re.sub(r"\s+", " ", raw_key).lower()
            kv_map[norm_key] = raw_val
            i += 1
            continue
            
        # Match "Key:" on this line and value on next line
        match_colon_end = re.match(r"^([A-Za-z0-9\s\/\-_#\(\)]+?)\s*[:：]$", line)
        if match_colon_end and i + 1 < len(lines):
            raw_key = match_colon_end.group(1).strip()
            next_line = lines[i + 1]
            if not next_line.endswith(":") and not next_line.endswith("："):
                norm_key = re.sub(r"\s+", " ", raw_key).lower()
                kv_map[norm_key] = next_line
                i += 2
                continue

        i += 1

    return kv_map


def _find_field(kv_map: Dict[str, str], candidate_keys: list) -> Optional[str]:
    """Helper to locate the first matching candidate key in the parsed key-value dictionary."""
    for key in candidate_keys:
        key_lower = key.lower()
        if key_lower in kv_map:
            return kv_map[key_lower]
        for existing_k, val in kv_map.items():
            if key_lower in existing_k:
                return val
    return None


def extract_registration_fields(text: str) -> Dict[str, Any]:
    """Parse registration certificate text into structured fields."""
    kv = parse_key_value_lines(text)
    
    company_name = _find_field(kv, [
        "company name", "legal name", "entity name", "business name", "registered name", "applicant name"
    ])
    reg_number = _find_field(kv, [
        "registration number", "reg no", "reg number", "company number", "registration no", "incorporation number", "cr number"
    ])
    country = _find_field(kv, [
        "country", "jurisdiction", "country of incorporation", "country of registration"
    ])
    
    return {
        "raw_text": text,
        "parsed_pairs": kv,
        "company_name": company_name,
        "registration_number": reg_number,
        "country": country,
    }


def extract_tax_fields(text: str) -> Dict[str, Any]:
    """Parse tax certificate text into structured fields."""
    kv = parse_key_value_lines(text)
    
    taxpayer_name = _find_field(kv, [
        "taxpayer name", "tax payer name", "company name", "name of taxpayer", "entity name", "legal name"
    ])
    tax_id = _find_field(kv, [
        "tax id", "tax identification number", "ein", "vat number", "gstin", "uen", "trn", "tax registration number", "vat id", "tax number"
    ])
    country = _find_field(kv, [
        "country", "tax jurisdiction", "issuing country", "jurisdiction"
    ])
    valid_until = _find_field(kv, [
        "valid until", "expiry date", "expiration date", "validity date", "valid through", "valid till", "expires on"
    ])
    
    return {
        "raw_text": text,
        "parsed_pairs": kv,
        "taxpayer_name": taxpayer_name,
        "tax_id": tax_id,
        "country": country,
        "valid_until": valid_until,
    }


def extract_bank_fields(text: str) -> Dict[str, Any]:
    """Parse bank letter text into structured fields."""
    kv = parse_key_value_lines(text)
    
    account_holder = _find_field(kv, [
        "account holder", "account holder name", "beneficiary name", "customer name", "name of account holder", "acc holder", "account name"
    ])
    bank_name = _find_field(kv, [
        "bank name", "financial institution", "institution name", "bank"
    ])
    account_number = _find_field(kv, [
        "account number", "iban", "bank account number", "account no", "acc no", "acc number"
    ])
    swift_bic = _find_field(kv, [
        "swift/bic", "swift", "bic", "swift code", "bic code", "swift / bic"
    ])
    
    return {
        "raw_text": text,
        "parsed_pairs": kv,
        "account_holder": account_holder,
        "bank_name": bank_name,
        "account_number": account_number,
        "swift_bic": swift_bic,
    }
