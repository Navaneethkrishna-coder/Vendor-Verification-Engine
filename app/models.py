from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class VerdictStatus(str, Enum):
    APPROVED = "Approved"
    PENDING = "Pending"
    REJECTED = "Rejected"


class StageStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    INFO = "INFO"


class VendorSubmission(BaseModel):
    legal_company_name: str
    trading_name: Optional[str] = None
    country: str
    address: str
    contact_name: str
    contact_email: str
    contact_phone: str
    registration_number: str
    tax_id: str
    bank_name: str
    bank_account_holder: str
    bank_account_number: str
    swift_bic: Optional[str] = None
    vendor_category: Optional[str] = "General"
    relationship_note: Optional[str] = None


class StageResult(BaseModel):
    stage_number: int
    stage_name: str
    status: StageStatus
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)
    risk_points: int = 0
    flag_type: Optional[str] = None  # e.g., 'fraud_duplicate_bank', 'fraud_tax_country', 'missing_fields', 'name_mismatch', etc.
    notes: List[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    run_id: str
    timestamp: str
    submission: VendorSubmission
    verdict: VerdictStatus
    risk_score: int
    primary_reason: str
    stages: List[StageResult] = Field(default_factory=list)
    vendor_message: Optional[str] = None
    is_returning_vendor: bool = False
    requires_escalation: bool = False
    reason_code: Optional[str] = None


class LedgerRecord(BaseModel):
    id: Optional[int] = None
    run_id: str
    company_name: str
    tax_id: str
    bank_account_number: str
    country: str
    verdict: str
    created_at: str
