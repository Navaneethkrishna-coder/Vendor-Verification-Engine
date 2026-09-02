import os
import io
import json
import asyncio
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.models import VendorSubmission, VerdictStatus
from app.database import (
    init_db,
    reset_db,
    get_runs,
    get_run,
    get_ledger_records
)
from app.sample_data import (
    SCENARIOS,
    generate_scenario_pdf_bytes,
    ensure_sample_pdfs_generated,
    SAMPLES_DIR
)
from app.engine import run_verification_engine

app = FastAPI(title="Vendor Onboarding Verification Process", version="1.0.0")

# Enable CORS for local development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Database and Sample PDFs on Startup
@app.on_event("startup")
async def on_startup():
    init_db()
    ensure_sample_pdfs_generated()


# -------------------------------------------------------------
# REST & SSE API ENDPOINTS
# -------------------------------------------------------------

@app.get("/api/scenarios")
async def list_scenarios():
    """Returns list of pre-configured demonstration scenarios."""
    scenarios_list = []
    for key, sc in SCENARIOS.items():
        scenarios_list.append({
            "key": key,
            "id": sc["id"],
            "name": sc["name"],
            "expected_verdict": sc["expected_verdict"],
            "badge_color": sc["badge_color"],
            "description": sc["description"],
            "form_data": sc["form_data"]
        })
    return scenarios_list


@app.get("/api/scenarios/{scenario_key}")
async def get_scenario_detail(scenario_key: str):
    """Get full scenario details including form data."""
    scenario = SCENARIOS.get(scenario_key)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


@app.get("/api/download-sample-pdf/{scenario_key}/{doc_key}")
async def download_sample_pdf(scenario_key: str, doc_key: str):
    """Download a generated sample PDF for a given scenario."""
    if scenario_key not in SCENARIOS:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if doc_key not in ["registration_certificate", "tax_certificate", "bank_letter"]:
        raise HTTPException(status_code=400, detail="Invalid doc_key")
    
    pdf_bytes = generate_scenario_pdf_bytes(scenario_key, doc_key)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{scenario_key}_{doc_key}.pdf"'}
    )


@app.post("/api/verify")
async def verify_vendor_sync(
    legal_company_name: str = Form(...),
    trading_name: Optional[str] = Form(None),
    country: str = Form(...),
    address: str = Form(...),
    contact_name: str = Form(...),
    contact_email: str = Form(...),
    contact_phone: str = Form(...),
    registration_number: str = Form(...),
    tax_id: str = Form(...),
    bank_name: str = Form(...),
    bank_account_holder: str = Form(...),
    bank_account_number: str = Form(...),
    swift_bic: Optional[str] = Form(None),
    vendor_category: Optional[str] = Form("General"),
    relationship_note: Optional[str] = Form(None),
    registration_certificate: Optional[UploadFile] = File(None),
    tax_certificate: Optional[UploadFile] = File(None),
    bank_letter: Optional[UploadFile] = File(None)
):
    """Synchronous verification endpoint."""
    submission = VendorSubmission(
        legal_company_name=legal_company_name,
        trading_name=trading_name or None,
        country=country,
        address=address,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        registration_number=registration_number,
        tax_id=tax_id,
        bank_name=bank_name,
        bank_account_holder=bank_account_holder,
        bank_account_number=bank_account_number,
        swift_bic=swift_bic or None,
        vendor_category=vendor_category or "General",
        relationship_note=relationship_note or None,
    )

    docs = {}
    if registration_certificate:
        docs["registration_certificate"] = await registration_certificate.read()
    if tax_certificate:
        docs["tax_certificate"] = await tax_certificate.read()
    if bank_letter:
        docs["bank_letter"] = await bank_letter.read()

    last_result = None
    async for event in run_verification_engine(submission, docs):
        if event["event"] == "complete":
            last_result = event["result"]

    return last_result


@app.post("/api/verify-stream")
async def verify_vendor_stream(
    legal_company_name: str = Form(""),
    trading_name: Optional[str] = Form(None),
    country: str = Form(""),
    address: str = Form(""),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    registration_number: str = Form(""),
    tax_id: str = Form(""),
    bank_name: str = Form(""),
    bank_account_holder: str = Form(""),
    bank_account_number: str = Form(""),
    swift_bic: Optional[str] = Form(None),
    vendor_category: Optional[str] = Form("General"),
    relationship_note: Optional[str] = Form(None),
    scenario_preset: Optional[str] = Form(None),
    registration_certificate: Optional[UploadFile] = File(None),
    tax_certificate: Optional[UploadFile] = File(None),
    bank_letter: Optional[UploadFile] = File(None)
):
    """
    Live Server-Sent Events (SSE) streaming verification endpoint.
    Computes each stage sequentially and streams updates in real time.
    """
    submission = VendorSubmission(
        legal_company_name=legal_company_name,
        trading_name=trading_name or None,
        country=country,
        address=address,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        registration_number=registration_number,
        tax_id=tax_id,
        bank_name=bank_name,
        bank_account_holder=bank_account_holder,
        bank_account_number=bank_account_number,
        swift_bic=swift_bic or None,
        vendor_category=vendor_category or "General",
        relationship_note=relationship_note or None,
    )

    docs = {}
    if registration_certificate and registration_certificate.filename:
        docs["registration_certificate"] = await registration_certificate.read()
    if tax_certificate and tax_certificate.filename:
        docs["tax_certificate"] = await tax_certificate.read()
    if bank_letter and bank_letter.filename:
        docs["bank_letter"] = await bank_letter.read()

    # If documents are not uploaded in form but scenario preset is specified, load generated scenario PDFs
    if scenario_preset and scenario_preset in SCENARIOS:
        if "registration_certificate" not in docs:
            docs["registration_certificate"] = generate_scenario_pdf_bytes(scenario_preset, "registration_certificate")
        if "tax_certificate" not in docs:
            docs["tax_certificate"] = generate_scenario_pdf_bytes(scenario_preset, "tax_certificate")
        if "bank_letter" not in docs:
            docs["bank_letter"] = generate_scenario_pdf_bytes(scenario_preset, "bank_letter")

    async def event_generator():
        try:
            async for payload in run_verification_engine(submission, docs):
                # Small yield pause to allow smooth SSE rendering
                await asyncio.sleep(0.35)
                event_name = payload.get("event", "message")
                data_str = json.dumps(payload)
                yield f"event: {event_name}\ndata: {data_str}\n\n"
        except Exception as e:
            error_payload = {"event": "error", "error": str(e)}
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/runs")
async def list_runs(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100),
    offset: int = Query(0)
):
    """Retrieve run history for the dashboard."""
    runs = get_runs(limit=limit, offset=offset, status=status, search=search)
    return {"runs": runs, "count": len(runs)}


@app.get("/api/runs/{run_id}")
async def get_single_run(run_id: str):
    """Retrieve detailed execution trace of a specific run."""
    run_data = get_run(run_id)
    if not run_data:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_data


@app.get("/api/ledger")
async def list_ledger_entries(limit: int = Query(100)):
    """Retrieve vendor ledger past decisions."""
    entries = get_ledger_records(limit=limit)
    return {"records": entries, "count": len(entries)}


@app.post("/api/reset-db")
async def reset_database():
    """Reset database tables for clean scenario demonstration."""
    reset_db()
    return {"message": "Database successfully reset"}


# -------------------------------------------------------------
# STATIC SPA FRONTEND SERVING
# -------------------------------------------------------------

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_frontend():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Vendor Verification Server Running</h1><p>Frontend index.html loading...</p>")
