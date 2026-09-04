import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.models import VerificationResult, LedgerRecord

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "vendor_onboarding.db")


def get_connection() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table 1: Full runs history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            country TEXT NOT NULL,
            verdict TEXT NOT NULL,
            risk_score INTEGER NOT NULL,
            primary_reason TEXT,
            vendor_message TEXT,
            reason_code TEXT,
            submission_json TEXT NOT NULL,
            stages_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    # Migration if reason_code column missing
    cursor.execute("PRAGMA table_info(runs)")
    columns = [col[1] for col in cursor.fetchall()]
    if "reason_code" not in columns:
        cursor.execute("ALTER TABLE runs ADD COLUMN reason_code TEXT")

    # Table 2: Vendor ledger for history checks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendor_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            company_name TEXT NOT NULL,
            tax_id TEXT NOT NULL,
            bank_account_number TEXT NOT NULL,
            country TEXT NOT NULL,
            verdict TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_bank ON vendor_ledger(bank_account_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_tax ON vendor_ledger(tax_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_company ON vendor_ledger(company_name)")
    
    conn.commit()
    conn.close()


def reset_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM runs")
    cursor.execute("DELETE FROM vendor_ledger")
    conn.commit()
    conn.close()


def save_run(result: VerificationResult):
    conn = get_connection()
    cursor = conn.cursor()
    
    submission_dict = result.submission.model_dump()
    stages_list = [s.model_dump() for s in result.stages]
    
    cursor.execute("""
        INSERT OR REPLACE INTO runs (
            run_id, company_name, country, verdict, risk_score,
            primary_reason, vendor_message, reason_code, submission_json, stages_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.run_id,
        result.submission.legal_company_name,
        result.submission.country,
        result.verdict.value,
        result.risk_score,
        result.primary_reason,
        result.vendor_message,
        result.reason_code,
        json.dumps(submission_dict),
        json.dumps(stages_list),
        result.timestamp
    ))

    # Always record into vendor ledger for historical cross-referencing
    cursor.execute("""
        INSERT INTO vendor_ledger (
            run_id, company_name, tax_id, bank_account_number, country, verdict, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        result.run_id,
        result.submission.legal_company_name,
        result.submission.tax_id.strip(),
        result.submission.bank_account_number.strip(),
        result.submission.country,
        result.verdict.value,
        result.timestamp
    ))

    conn.commit()
    conn.close()


def get_runs(limit: int = 100, offset: int = 0, status: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM runs WHERE 1=1"
    params: List[Any] = []
    
    if status:
        query += " AND verdict = ?"
        params.append(status)
    if search:
        query += " AND (company_name LIKE ? OR country LIKE ? OR run_id LIKE ?)"
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param])
        
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    results = []
    for r in rows:
        results.append({
            "run_id": r["run_id"],
            "company_name": r["company_name"],
            "country": r["country"],
            "verdict": r["verdict"],
            "risk_score": r["risk_score"],
            "primary_reason": r["primary_reason"],
            "vendor_message": r["vendor_message"],
            "reason_code": r["reason_code"] if "reason_code" in r.keys() else None,
            "submission": json.loads(r["submission_json"]),
            "stages": json.loads(r["stages_json"]),
            "created_at": r["created_at"]
        })
    conn.close()
    return results


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "company_name": row["company_name"],
        "country": row["country"],
        "verdict": row["verdict"],
        "risk_score": row["risk_score"],
        "primary_reason": row["primary_reason"],
        "vendor_message": row["vendor_message"],
        "reason_code": row["reason_code"] if "reason_code" in row.keys() else None,
        "submission": json.loads(row["submission_json"]),
        "stages": json.loads(row["stages_json"]),
        "created_at": row["created_at"]
    }


def get_ledger_records(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vendor_ledger ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    records = [dict(r) for r in rows]
    conn.close()
    return records


def find_bank_account_history(bank_account_number: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cleaned_acc = bank_account_number.strip().replace(" ", "").upper()
    cursor.execute("""
        SELECT * FROM vendor_ledger 
        WHERE REPLACE(UPPER(bank_account_number), ' ', '') = ?
          AND UPPER(verdict) IN ('APPROVED', 'PENDING')
        ORDER BY id DESC
    """, (cleaned_acc,))
    rows = cursor.fetchall()
    records = [dict(r) for r in rows]
    conn.close()
    return records


def find_tax_id_history(tax_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cleaned_tax = tax_id.strip().replace(" ", "").upper()
    cursor.execute("""
        SELECT * FROM vendor_ledger 
        WHERE REPLACE(UPPER(tax_id), ' ', '') = ?
        ORDER BY id DESC
    """, (cleaned_tax,))
    rows = cursor.fetchall()
    records = [dict(r) for r in rows]
    conn.close()
    return records
