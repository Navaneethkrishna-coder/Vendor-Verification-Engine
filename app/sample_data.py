import os
import io
from typing import Dict, Any, Tuple
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples")


def create_clean_pdf(title: str, subtitle: str, fields: Dict[str, str], footer_note: str = "") -> bytes:
    """Generate a clean, professional, machine-readable PDF with explicit 'Label: Value' lines."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E293B'),
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#64748B'),
        spaceAfter=15
    )
    label_style = ParagraphStyle(
        'FieldLabel',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#334155')
    )
    value_style = ParagraphStyle(
        'FieldValue',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        fontName='Helvetica',
        textColor=colors.HexColor('#0F172A')
    )
    footer_style = ParagraphStyle(
        'DocFooter',
        parent=styles['Italic'],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#94A3B8')
    )

    story = [
        Paragraph(title, title_style),
        Paragraph(subtitle, subtitle_style),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#CBD5E1'), spaceAfter=15)
    ]

    table_data = []
    for label, val in fields.items():
        table_data.append([
            Paragraph(f"{label}:", label_style),
            Paragraph(str(val), value_style)
        ])

    t = Table(table_data, colWidths=[180, 350])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#F1F5F9'))
    ]))
    story.append(t)

    if footer_note:
        story.append(Spacer(1, 25))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0'), spaceAfter=8))
        story.append(Paragraph(footer_note, footer_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# Base Document templates for reuse across test variants
DOC_BLUEWAVE_REG = {
    "title": "Certificate of Incorporation",
    "subtitle": "State of Delaware - Division of Corporations",
    "fields": {
        "Company Name": "Bluewave Logistics Inc",
        "Registration Number": "US-DE-4471829",
        "Country": "United States",
        "Incorporation Date": "2018-04-12"
    },
    "footer": "Official certification of valid corporate existence under Delaware General Corporation Law."
}

DOC_BLUEWAVE_TAX = {
    "title": "Tax Identification & Status Certificate",
    "subtitle": "Department of the Treasury - Internal Revenue Service",
    "fields": {
        "Taxpayer Name": "Bluewave Logistics Inc",
        "Tax ID": "47-3829104",
        "Country": "United States",
        "Valid Until": "2027-12-31"
    },
    "footer": "Form 147C - Verification of Federal Employer Identification Number."
}

DOC_BLUEWAVE_BANK = {
    "title": "Bank Account Confirmation Letter",
    "subtitle": "First Continental Bank - Commercial Accounts Division",
    "fields": {
        "Account Holder": "Bluewave Logistics Inc",
        "Bank Name": "First Continental Bank",
        "Account Number": "000123456789",
        "SWIFT/BIC": "FCBKUS33",
        "Currency": "USD"
    },
    "footer": "This letter certifies that the account is active and in good standing."
}

DOC_MERIDIAN_REG = {
    "title": "Certificate of Formation - Limited Liability Company",
    "subtitle": "New York Department of State - Division of Corporations",
    "fields": {
        "Company Name": "Meridian Traders LLC",
        "Registration Number": "US-NY-9012734",
        "Country": "United States"
    },
    "footer": "Filed in accordance with Section 203 of the NY Limited Liability Company Law."
}

DOC_MERIDIAN_TAX = {
    "title": "State Certificate of Tax Registration",
    "subtitle": "Department of Taxation and Finance",
    "fields": {
        "Taxpayer Name": "Meridian Traders LLC",
        "Tax ID": "GB998877665",
        "Country": "United States",
        "Valid Until": "2027-11-30"
    },
    "footer": "Certificate of Authority."
}

DOC_MERIDIAN_BANK = {
    "title": "Commercial Banking Account Verification",
    "subtitle": "Continental Trust Bank",
    "fields": {
        "Account Holder": "Meridian Traders LLC",
        "Bank Name": "Continental Trust Bank",
        "Account Number": "000998877221",
        "SWIFT/BIC": "CTBKUS44"
    },
    "footer": "Confirmed active account."
}


SCENARIOS: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # Scenario 1: Happy Path -> Approved
    # -------------------------------------------------------------------------
    "scenario_1_approved": {
        "id": "scenario_1_approved",
        "name": "1. Bluewave Logistics (US) - Happy Path",
        "expected_verdict": "Approved",
        "badge_color": "green",
        "description": "Clean US submission. All names, registration number, tax ID, and bank account match across form and all 3 documents.",
        "form_data": {
            "legal_company_name": "Bluewave Logistics Inc",
            "trading_name": "",
            "country": "United States",
            "address": "500 Harbor Way, Wilmington, DE",
            "contact_name": "Dana Cole",
            "contact_email": "dana.cole@bluewavelogistics.com",
            "contact_phone": "+1-302-555-0148",
            "registration_number": "US-DE-4471829",
            "tax_id": "47-3829104",
            "bank_name": "First Continental Bank",
            "bank_account_holder": "Bluewave Logistics Inc",
            "bank_account_number": "000123456789",
            "swift_bic": "FCBKUS33",
            "vendor_category": "Logistics & Freight",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": DOC_BLUEWAVE_REG,
            "tax_certificate": DOC_BLUEWAVE_TAX,
            "bank_letter": DOC_BLUEWAVE_BANK
        }
    },

    # -------------------------------------------------------------------------
    # Scenario 2: Wrong Company Documents Attached -> Rejected
    # -------------------------------------------------------------------------
    "scenario_2_wrong_company_docs": {
        "id": "scenario_2_wrong_company_docs",
        "name": "2. Wrong Company Documents Attached (Bluewave vs Meridian)",
        "expected_verdict": "Rejected",
        "badge_color": "red",
        "description": "Bluewave application submitted with Meridian Traders LLC's registration and tax certs attached. Critical inconsistency -> Rejected.",
        "form_data": {
            "legal_company_name": "Bluewave Logistics Inc",
            "trading_name": "",
            "country": "United States",
            "address": "500 Harbor Way, Wilmington, DE",
            "contact_name": "Dana Cole",
            "contact_email": "dana.cole@bluewavelogistics.com",
            "contact_phone": "+1-302-555-0148",
            "registration_number": "US-DE-4471829",
            "tax_id": "47-3829104",
            "bank_name": "First Continental Bank",
            "bank_account_holder": "Bluewave Logistics Inc",
            "bank_account_number": "000123456789",
            "swift_bic": "FCBKUS33",
            "vendor_category": "Logistics & Freight",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": DOC_MERIDIAN_REG, # Meridian Traders LLC
            "tax_certificate": DOC_MERIDIAN_TAX,         # Meridian Traders LLC
            "bank_letter": DOC_BLUEWAVE_BANK
        }
    },

    # -------------------------------------------------------------------------
    # Scenario 3: Form Field Typo / Mismatch -> Pending
    # -------------------------------------------------------------------------
    "scenario_3_field_typo_pending": {
        "id": "scenario_3_field_typo_pending",
        "name": "3. Form Field Discrepancy (Account No. Typo)",
        "expected_verdict": "Pending",
        "badge_color": "amber",
        "description": "Form specifies account '999999999999' while bank letter shows '000123456789'. Fixable gap -> Pending (quotes both values).",
        "form_data": {
            "legal_company_name": "Bluewave Logistics Inc",
            "trading_name": "",
            "country": "United States",
            "address": "500 Harbor Way, Wilmington, DE",
            "contact_name": "Dana Cole",
            "contact_email": "dana.cole@bluewavelogistics.com",
            "contact_phone": "+1-302-555-0148",
            "registration_number": "US-DE-4471829",
            "tax_id": "47-3829104",
            "bank_name": "First Continental Bank",
            "bank_account_holder": "Bluewave Logistics Inc",
            "bank_account_number": "999999999999",  # TYPO vs 000123456789 in doc
            "swift_bic": "FCBKUS33",
            "vendor_category": "Logistics & Freight",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": DOC_BLUEWAVE_REG,
            "tax_certificate": DOC_BLUEWAVE_TAX,
            "bank_letter": DOC_BLUEWAVE_BANK
        }
    },
    
    # -------------------------------------------------------------------------
    # Scenario 4a: Legitimate Name Mismatch (Parent Bank / No Note) -> Pending
    # -------------------------------------------------------------------------
    "scenario_4a_pending": {
        "id": "scenario_4a_pending",
        "name": "4a. Nimbus Retail (UK) - Parent Bank (No Note)",
        "expected_verdict": "Pending",
        "badge_color": "amber",
        "description": "UK submission where bank account is held by parent entity (Nimbus Group Holdings Ltd) with no explanation note. Needs clarification.",
        "form_data": {
            "legal_company_name": "Nimbus Retail Ltd",
            "trading_name": "Nimbus Retail",
            "country": "United Kingdom",
            "address": "14 Market Street, Manchester, UK",
            "contact_name": "Priya Shah",
            "contact_email": "priya.shah@nimbusretail.co.uk",
            "contact_phone": "+44 161 555 0199",
            "registration_number": "UK-08847213",
            "tax_id": "GB204471938",
            "bank_name": "Highstreet Bank plc",
            "bank_account_holder": "Nimbus Group Holdings Ltd",
            "bank_account_number": "GB29NWBK60161331926819",
            "swift_bic": "NWBKGB2L",
            "vendor_category": "Retail",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": {
                "title": "Certificate of Incorporation of a Public Limited Company",
                "subtitle": "Companies House - Cardiff",
                "fields": {
                    "Company Name": "Nimbus Retail Ltd",
                    "Registration Number": "UK-08847213",
                    "Country": "United Kingdom"
                },
                "footer": "Certified under the Companies Act 2006."
            },
            "tax_certificate": {
                "title": "Certificate of VAT Registration",
                "subtitle": "HM Revenue & Customs",
                "fields": {
                    "Taxpayer Name": "Nimbus Retail Ltd",
                    "Tax ID": "GB204471938",
                    "Country": "United Kingdom",
                    "Valid Until": "2028-03-31"
                },
                "footer": "Value Added Tax Registration Schedule."
            },
            "bank_letter": {
                "title": "Account Verification Schedule",
                "subtitle": "Highstreet Bank plc - Corporate Banking Services",
                "fields": {
                    "Account Holder": "Nimbus Group Holdings Ltd",
                    "Bank Name": "Highstreet Bank plc",
                    "Account Number": "GB29NWBK60161331926819",
                    "SWIFT/BIC": "NWBKGB2L"
                },
                "footer": "Account verified for commercial operations."
            }
        }
    },

    # -------------------------------------------------------------------------
    # Scenario 4b: Legitimate Name Mismatch (Parent Bank / WITH Note) -> Pending
    # -------------------------------------------------------------------------
    "scenario_4b_approved": {
        "id": "scenario_4b_approved",
        "name": "4b. Nimbus Retail (UK) - Parent Bank (WITH Note)",
        "expected_verdict": "Pending",
        "badge_color": "amber",
        "description": "Identical to 4a, but includes vendor explanation note ('Banking is handled by our parent company...'). Surfaces explanation for rapid reviewer sign-off -> Pending.",
        "form_data": {
            "legal_company_name": "Nimbus Retail Ltd",
            "trading_name": "Nimbus Retail",
            "country": "United Kingdom",
            "address": "14 Market Street, Manchester, UK",
            "contact_name": "Priya Shah",
            "contact_email": "priya.shah@nimbusretail.co.uk",
            "contact_phone": "+44 161 555 0199",
            "registration_number": "UK-08847213",
            "tax_id": "GB204471938",
            "bank_name": "Highstreet Bank plc",
            "bank_account_holder": "Nimbus Group Holdings Ltd",
            "bank_account_number": "GB29NWBK60161331926819",
            "swift_bic": "NWBKGB2L",
            "vendor_category": "Retail",
            "relationship_note": "Banking is handled by our parent company, Nimbus Group Holdings Ltd."
        },
        "documents": {
            "registration_certificate": {
                "title": "Certificate of Incorporation of a Public Limited Company",
                "subtitle": "Companies House - Cardiff",
                "fields": {
                    "Company Name": "Nimbus Retail Ltd",
                    "Registration Number": "UK-08847213",
                    "Country": "United Kingdom"
                },
                "footer": "Certified under the Companies Act 2006."
            },
            "tax_certificate": {
                "title": "Certificate of VAT Registration",
                "subtitle": "HM Revenue & Customs",
                "fields": {
                    "Taxpayer Name": "Nimbus Retail Ltd",
                    "Tax ID": "GB204471938",
                    "Country": "United Kingdom",
                    "Valid Until": "2028-03-31"
                },
                "footer": "Value Added Tax Registration Schedule."
            },
            "bank_letter": {
                "title": "Account Verification Schedule",
                "subtitle": "Highstreet Bank plc - Corporate Banking Services",
                "fields": {
                    "Account Holder": "Nimbus Group Holdings Ltd",
                    "Bank Name": "Highstreet Bank plc",
                    "Account Number": "GB29NWBK60161331926819",
                    "SWIFT/BIC": "NWBKGB2L"
                },
                "footer": "Account verified for commercial operations."
            }
        }
    },

    # -------------------------------------------------------------------------
    # Scenario 5: Tax ID / Country Fraud -> Rejected
    # -------------------------------------------------------------------------
    "scenario_5_rejected": {
        "id": "scenario_5_rejected",
        "name": "5. Meridian Traders (US) - Tax ID Country Fraud",
        "expected_verdict": "Rejected",
        "badge_color": "red",
        "description": "Declares United States jurisdiction, but tax ID is definitively formatted as a UK VAT number (GB998877665). Hard fraud signal.",
        "form_data": {
            "legal_company_name": "Meridian Traders LLC",
            "trading_name": "",
            "country": "United States",
            "address": "88 Fifth Ave, New York, NY",
            "contact_name": "Jordan Lee",
            "contact_email": "jordan.lee@meridiantraders.com",
            "contact_phone": "+1-212-555-0173",
            "registration_number": "US-NY-9012734",
            "tax_id": "GB998877665",
            "bank_name": "Continental Trust Bank",
            "bank_account_holder": "Meridian Traders LLC",
            "bank_account_number": "000998877221",
            "swift_bic": "CTBKUS44",
            "vendor_category": "General Merchandise",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": DOC_MERIDIAN_REG,
            "tax_certificate": DOC_MERIDIAN_TAX,
            "bank_letter": DOC_MERIDIAN_BANK
        }
    },

    # -------------------------------------------------------------------------
    # Scenario 6a & 6b: Duplicate Bank Account Reuse
    # -------------------------------------------------------------------------
    "scenario_6a_seed_vantage": {
        "id": "scenario_6a_seed_vantage",
        "name": "6a. Seed History - Vantage Freight (DE)",
        "expected_verdict": "Approved",
        "badge_color": "green",
        "description": "Legitimate German vendor onboarding. Registers bank account DE89370400440532013000 in the ledger.",
        "form_data": {
            "legal_company_name": "Vantage Freight Co",
            "trading_name": "",
            "country": "Germany",
            "address": "Speicherstadt 12, Hamburg, Germany",
            "contact_name": "Klaus Weber",
            "contact_email": "klaus.weber@vantagefreight.de",
            "contact_phone": "+49 40 555 0110",
            "registration_number": "DE-HRB-118820",
            "tax_id": "DE811234567",
            "bank_name": "Deutsche Handelsbank",
            "bank_account_holder": "Vantage Freight Co",
            "bank_account_number": "DE89370400440532013000",
            "swift_bic": "DHBKDEFF",
            "vendor_category": "Logistics",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": {
                "title": "Handelsregisterauszug (Commercial Register Extract)",
                "subtitle": "Amtsgericht Hamburg - Registergericht",
                "fields": {
                    "Company Name": "Vantage Freight Co",
                    "Registration Number": "DE-HRB-118820",
                    "Country": "Germany"
                },
                "footer": "Amtlicher Registerauszug."
            },
            "tax_certificate": {
                "title": "Bescheinigung in Steuersachen (Tax Clearance Certificate)",
                "subtitle": "Finanzamt Hamburg-Mitte",
                "fields": {
                    "Taxpayer Name": "Vantage Freight Co",
                    "Tax ID": "DE811234567",
                    "Country": "Germany",
                    "Valid Until": "2028-12-31"
                },
                "footer": "Umsatzsteuer-Identifikationsnummer nach § 27a UStG."
            },
            "bank_letter": {
                "title": "Bankbestätigung (Bank Confirmation)",
                "subtitle": "Deutsche Handelsbank AG",
                "fields": {
                    "Account Holder": "Vantage Freight Co",
                    "Bank Name": "Deutsche Handelsbank",
                    "Account Number": "DE89370400440532013000",
                    "SWIFT/BIC": "DHBKDEFF"
                },
                "footer": "Bestätigung der bestehenden Geschäftsverbindung."
            }
        }
    },

    "scenario_6b_sterling_duplicate": {
        "id": "scenario_6b_sterling_duplicate",
        "name": "6b. Sterling Freight (DE) - Duplicate Bank Account Reuse",
        "expected_verdict": "Rejected",
        "badge_color": "red",
        "description": "Different company attempting to register the EXACT bank account already on file for Vantage Freight. Overrides all checks -> Rejected.",
        "form_data": {
            "legal_company_name": "Sterling Freight Partners",
            "trading_name": "",
            "country": "Germany",
            "address": "Rheinuferstrasse 4, Cologne, Germany",
            "contact_name": "Anna Fischer",
            "contact_email": "anna.fischer@sterlingfreight.de",
            "contact_phone": "+49 221 555 0142",
            "registration_number": "DE-HRB-227341",
            "tax_id": "DE900112233",
            "bank_name": "Deutsche Handelsbank",
            "bank_account_holder": "Sterling Freight Partners",
            "bank_account_number": "DE89370400440532013000",
            "swift_bic": "DHBKDEFF",
            "vendor_category": "Logistics",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": {
                "title": "Handelsregisterauszug (Commercial Register Extract)",
                "subtitle": "Amtsgericht Köln - Registergericht",
                "fields": {
                    "Company Name": "Sterling Freight Partners",
                    "Registration Number": "DE-HRB-227341",
                    "Country": "Germany"
                },
                "footer": "Amtlicher Registerauszug."
            },
            "tax_certificate": {
                "title": "Bescheinigung in Steuersachen",
                "subtitle": "Finanzamt Köln-Altstadt",
                "fields": {
                    "Taxpayer Name": "Sterling Freight Partners",
                    "Tax ID": "DE900112233",
                    "Country": "Germany",
                    "Valid Until": "2028-09-30"
                },
                "footer": "Gültige Steuerbescheinigung."
            },
            "bank_letter": {
                "title": "Bankbestätigung",
                "subtitle": "Deutsche Handelsbank AG",
                "fields": {
                    "Account Holder": "Sterling Freight Partners",
                    "Bank Name": "Deutsche Handelsbank",
                    "Account Number": "DE89370400440532013000",
                    "SWIFT/BIC": "DHBKDEFF"
                },
                "footer": "Bankverbindung."
            }
        }
    },

    # -------------------------------------------------------------------------
    # Scenario 7a & 7b: Returning Vendor with Expired Tax Certificate
    # -------------------------------------------------------------------------
    "scenario_7a_seed_anchor": {
        "id": "scenario_7a_seed_anchor",
        "name": "7a. Seed History - Anchor Supplies (IN)",
        "expected_verdict": "Approved",
        "badge_color": "green",
        "description": "Initial clean submission for Indian vendor with valid tax certificate (valid until 2027-06-30).",
        "form_data": {
            "legal_company_name": "Anchor Supplies Pvt Ltd",
            "trading_name": "",
            "country": "India",
            "address": "Plot 42, MIDC, Pune, India",
            "contact_name": "Rohan Mehta",
            "contact_email": "rohan.mehta@anchorsupplies.in",
            "contact_phone": "+91 98765 43210",
            "registration_number": "IN-U29100-2016",
            "tax_id": "27AAAAA0000A1Z5",
            "bank_name": "National Trust Bank of India",
            "bank_account_holder": "Anchor Supplies Pvt Ltd",
            "bank_account_number": "INNTB0001234567890",
            "swift_bic": "NTBIINBB",
            "vendor_category": "Industrial Supplies",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": {
                "title": "Certificate of Incorporation",
                "subtitle": "Ministry of Corporate Affairs - Registrar of Companies, Pune",
                "fields": {
                    "Company Name": "Anchor Supplies Pvt Ltd",
                    "Registration Number": "IN-U29100-2016",
                    "Country": "India"
                },
                "footer": "Issued pursuant to section 7 of the Companies Act, 2013."
            },
            "tax_certificate": {
                "title": "GST Registration Certificate (Form GST REG-06)",
                "subtitle": "Government of India - Goods and Services Tax",
                "fields": {
                    "Taxpayer Name": "Anchor Supplies Pvt Ltd",
                    "Tax ID": "27AAAAA0000A1Z5",
                    "Country": "India",
                    "Valid Until": "2027-06-30"
                },
                "footer": "Registration Certificate issued under Section 25 of the CGST Act."
            },
            "bank_letter": {
                "title": "Bank Mandate Verification Letter",
                "subtitle": "National Trust Bank of India - Corporate Banking",
                "fields": {
                    "Account Holder": "Anchor Supplies Pvt Ltd",
                    "Bank Name": "National Trust Bank of India",
                    "Account Number": "INNTB0001234567890",
                    "SWIFT/BIC": "NTBIINBB"
                },
                "footer": "Verified signature and active account mandate."
            }
        }
    },

    "scenario_7b_anchor_expired": {
        "id": "scenario_7b_anchor_expired",
        "name": "7b. Anchor Supplies (IN) - Returning Vendor (Expired Tax Cert)",
        "expected_verdict": "Pending",
        "badge_color": "amber",
        "description": "Returning vendor with prior approval, resubmitting with an expired tax certificate (Valid Until: 2025-06-30). Lightweight Pending asking only for renewed tax certificate.",
        "form_data": {
            "legal_company_name": "Anchor Supplies Pvt Ltd",
            "trading_name": "",
            "country": "India",
            "address": "Plot 42, MIDC, Pune, India",
            "contact_name": "Rohan Mehta",
            "contact_email": "rohan.mehta@anchorsupplies.in",
            "contact_phone": "+91 98765 43210",
            "registration_number": "IN-U29100-2016",
            "tax_id": "27AAAAA0000A1Z5",
            "bank_name": "National Trust Bank of India",
            "bank_account_holder": "Anchor Supplies Pvt Ltd",
            "bank_account_number": "INNTB0001234567890",
            "swift_bic": "NTBIINBB",
            "vendor_category": "Industrial Supplies",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": {
                "title": "Certificate of Incorporation",
                "subtitle": "Ministry of Corporate Affairs - Registrar of Companies, Pune",
                "fields": {
                    "Company Name": "Anchor Supplies Pvt Ltd",
                    "Registration Number": "IN-U29100-2016",
                    "Country": "India"
                },
                "footer": "Issued pursuant to section 7 of the Companies Act, 2013."
            },
            "tax_certificate": {
                "title": "GST Registration Certificate (Form GST REG-06)",
                "subtitle": "Government of India - Goods and Services Tax",
                "fields": {
                    "Taxpayer Name": "Anchor Supplies Pvt Ltd",
                    "Tax ID": "27AAAAA0000A1Z5",
                    "Country": "India",
                    "Valid Until": "2025-06-30"  # Expired date
                },
                "footer": "Registration Certificate issued under Section 25 of the CGST Act."
            },
            "bank_letter": {
                "title": "Bank Mandate Verification Letter",
                "subtitle": "National Trust Bank of India - Corporate Banking",
                "fields": {
                    "Account Holder": "Anchor Supplies Pvt Ltd",
                    "Bank Name": "National Trust Bank of India",
                    "Account Number": "INNTB0001234567890",
                    "SWIFT/BIC": "NTBIINBB"
                },
                "footer": "Verified signature and active account mandate."
            }
        }
    },

    # -------------------------------------------------------------------------
    # Scenario 8: Sanctions Hard Match -> Rejected
    # -------------------------------------------------------------------------
    "scenario_8_sanctions_hard_match": {
        "id": "scenario_8_sanctions_hard_match",
        "name": "8. Talon Sentinel Trading Co (US) - Sanctions Hard Match",
        "expected_verdict": "Rejected",
        "badge_color": "red",
        "description": "Exact match to restricted-party list (Talon Sentinel Trading Co). Statutory compliance stop overrides all other checks -> Rejected.",
        "form_data": {
            "legal_company_name": "Talon Sentinel Trading Co",
            "trading_name": "",
            "country": "United States",
            "address": "1200 North Market St, Wilmington, DE",
            "contact_name": "Marcus Vance",
            "contact_email": "m.vance@talonsentinel.com",
            "contact_phone": "+1-302-555-0839",
            "registration_number": "US-DE-8192045",
            "tax_id": "82-1946285",
            "bank_name": "Apex Commercial Bank",
            "bank_account_holder": "Talon Sentinel Trading Co",
            "bank_account_number": "440012849103",
            "swift_bic": "APEXUS33",
            "vendor_category": "Logistics & Freight",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": {
                "title": "Certificate of Incorporation",
                "subtitle": "State of Delaware - Division of Corporations",
                "fields": {
                    "Company Name": "Talon Sentinel Trading Co",
                    "Registration Number": "US-DE-8192045",
                    "Country": "United States",
                    "Incorporation Date": "2019-06-15"
                },
                "footer": "Official certification of valid corporate existence under Delaware General Corporation Law."
            },
            "tax_certificate": {
                "title": "Tax Identification & Status Certificate",
                "subtitle": "Department of the Treasury - Internal Revenue Service",
                "fields": {
                    "Taxpayer Name": "Talon Sentinel Trading Co",
                    "Tax ID": "82-1946285",
                    "Country": "United States",
                    "Valid Until": "2028-12-31"
                },
                "footer": "Form 147C - Verification of Federal Employer Identification Number."
            },
            "bank_letter": {
                "title": "Bank Account Confirmation Letter",
                "subtitle": "Apex Commercial Bank - Corporate Accounts",
                "fields": {
                    "Account Holder": "Talon Sentinel Trading Co",
                    "Bank Name": "Apex Commercial Bank",
                    "Account Number": "440012849103",
                    "SWIFT/BIC": "APEXUS33",
                    "Currency": "USD"
                },
                "footer": "This letter certifies that the account is active and in good standing."
            }
        }
    },

    # -------------------------------------------------------------------------
    # Scenario 9: Sanctions Moderate Match -> Pending (sanctions_review)
    # -------------------------------------------------------------------------
    "scenario_9_sanctions_moderate_match": {
        "id": "scenario_9_sanctions_moderate_match",
        "name": "9. Talon Sentinal Trading Company (US) - Sanctions Review",
        "expected_verdict": "Pending",
        "badge_color": "amber",
        "description": "Applicant 'Talon Sentinal Trading Company' shows ~81% similarity to restricted party 'Talon Sentinel Trading Co'. Requires manual compliance review -> Pending.",
        "form_data": {
            "legal_company_name": "Talon Sentinal Trading Company",
            "trading_name": "",
            "country": "United States",
            "address": "700 Delaware Ave, Wilmington, DE",
            "contact_name": "Julian Vance",
            "contact_email": "j.vance@talonsentinal.com",
            "contact_phone": "+1-302-555-0191",
            "registration_number": "US-DE-6391052",
            "tax_id": "93-5182940",
            "bank_name": "First Liberty National Bank",
            "bank_account_holder": "Talon Sentinal Trading Company",
            "bank_account_number": "550098712345",
            "swift_bic": "FLNBUS33",
            "vendor_category": "Logistics & Freight",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": {
                "title": "Certificate of Incorporation",
                "subtitle": "State of Delaware - Division of Corporations",
                "fields": {
                    "Company Name": "Talon Sentinal Trading Company",
                    "Registration Number": "US-DE-6391052",
                    "Country": "United States",
                    "Incorporation Date": "2019-06-15"
                },
                "footer": "Official certification of valid corporate existence under Delaware General Corporation Law."
            },
            "tax_certificate": {
                "title": "Tax Identification & Status Certificate",
                "subtitle": "Department of the Treasury - Internal Revenue Service",
                "fields": {
                    "Taxpayer Name": "Talon Sentinal Trading Company",
                    "Tax ID": "93-5182940",
                    "Country": "United States",
                    "Valid Until": "2028-12-31"
                },
                "footer": "Form 147C - Verification of Federal Employer Identification Number."
            },
            "bank_letter": {
                "title": "Bank Account Confirmation Letter",
                "subtitle": "First Liberty National Bank - Commercial Accounts Division",
                "fields": {
                    "Account Holder": "Talon Sentinal Trading Company",
                    "Bank Name": "First Liberty National Bank",
                    "Account Number": "550098712345",
                    "SWIFT/BIC": "FLNBUS33",
                    "Currency": "USD"
                },
                "footer": "This letter certifies that the account is active and in good standing."
            }
        }
    },

    # -------------------------------------------------------------------------
    # Scenario 10: Embargoed Country -> Rejected
    # -------------------------------------------------------------------------
    "scenario_10_embargoed_country": {
        "id": "scenario_10_embargoed_country",
        "name": "10. Bluewave Logistics (Freedonia) - Embargoed Country",
        "expected_verdict": "Rejected",
        "badge_color": "red",
        "description": "Declares country 'Freedonia' which is on the embargoed jurisdiction list. Mandatory compliance stop overrides all other checks -> Rejected.",
        "form_data": {
            "legal_company_name": "Bluewave Logistics Inc",
            "trading_name": "",
            "country": "Freedonia",
            "address": "12 Freedom Plaza, Capital City, Freedonia",
            "contact_name": "Dana Cole",
            "contact_email": "dana.cole@bluewavelogistics.com",
            "contact_phone": "+1-302-555-0148",
            "registration_number": "FD-CR-9021843",
            "tax_id": "FD-8839201",
            "bank_name": "Freedonia Commercial Bank",
            "bank_account_holder": "Bluewave Logistics Inc",
            "bank_account_number": "770012948192",
            "swift_bic": "FCBKUS33",
            "vendor_category": "Logistics & Freight",
            "relationship_note": ""
        },
        "documents": {
            "registration_certificate": {
                "title": "Certificate of Incorporation",
                "subtitle": "Ministry of Commerce - Freedonia",
                "fields": {
                    "Company Name": "Bluewave Logistics Inc",
                    "Registration Number": "FD-CR-9021843",
                    "Country": "Freedonia",
                    "Incorporation Date": "2018-04-12"
                },
                "footer": "Official certification of corporate registry of Freedonia."
            },
            "tax_certificate": {
                "title": "Tax Identification & Status Certificate",
                "subtitle": "Ministry of Revenue - Freedonia",
                "fields": {
                    "Taxpayer Name": "Bluewave Logistics Inc",
                    "Tax ID": "FD-8839201",
                    "Country": "Freedonia",
                    "Valid Until": "2027-12-31"
                },
                "footer": "Certificate of Tax Registration - Freedonia Revenue Service."
            },
            "bank_letter": {
                "title": "Bank Account Confirmation Letter",
                "subtitle": "Freedonia Commercial Bank - Commercial Accounts Division",
                "fields": {
                    "Account Holder": "Bluewave Logistics Inc",
                    "Bank Name": "Freedonia Commercial Bank",
                    "Account Number": "770012948192",
                    "SWIFT/BIC": "FCBKUS33",
                    "Currency": "USD"
                },
                "footer": "This letter certifies that the account is active and in good standing."
            }
        }
    }
}


def generate_scenario_pdf_bytes(scenario_key: str, doc_key: str) -> bytes:
    """Generate real PDF bytes for a given scenario document."""
    scenario = SCENARIOS.get(scenario_key)
    if not scenario:
        raise ValueError(f"Unknown scenario key: {scenario_key}")
    
    doc_def = scenario["documents"].get(doc_key)
    if not doc_def:
        raise ValueError(f"Unknown document key: {doc_key} for scenario {scenario_key}")
    
    return create_clean_pdf(
        title=doc_def["title"],
        subtitle=doc_def["subtitle"],
        fields=doc_def["fields"],
        footer_note=doc_def.get("footer", "")
    )


def ensure_sample_pdfs_generated() -> Dict[str, Dict[str, str]]:
    """Generate physical sample PDF files in samples/ for download or manual inspection."""
    os.makedirs(SAMPLES_DIR, exist_ok=True)
    generated_paths: Dict[str, Dict[str, str]] = {}
    
    for s_key, s_data in SCENARIOS.items():
        generated_paths[s_key] = {}
        for doc_key in ["registration_certificate", "tax_certificate", "bank_letter"]:
            filename = f"{s_key}_{doc_key}.pdf"
            filepath = os.path.join(SAMPLES_DIR, filename)
            pdf_bytes = generate_scenario_pdf_bytes(s_key, doc_key)
            with open(filepath, "wb") as f:
                f.write(pdf_bytes)
            generated_paths[s_key][doc_key] = filepath
            
    return generated_paths
