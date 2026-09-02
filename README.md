# Intake — Vendor Verification Process

A working, live-runnable process for vendor onboarding (PS-2): a submission
comes in, the process validates it, cross-references every document field
against the form and against prior submissions, and produces **Approved /
Pending / Rejected** with the reasoning attached — and, for anything not
approved, a specific message back to the vendor about exactly what's needed.

## Run it (one command)

```bash
cd backend
pip install -r requirements.txt
python3 sample_data/make_pdfs.py     # generates the sample PDFs once
uvicorn app.main:app --reload
```

Open **http://localhost:8000** — that's it. The FastAPI backend serves the
frontend directly, so there's no separate dev server to keep alive during a
demo.

Optional: set `ANTHROPIC_API_KEY` in your environment to have the vendor
follow-up message polished by Claude instead of the built-in template. Not
required — the pipeline works identically either way (see "AI usage" below).

## What's actually running

- **Backend**: Python / FastAPI. `app/engine.py` is the rules engine —
  every check is a small, pure function so each decision is inspectable and
  testable on its own.
- **Documents**: real PDFs, parsed with `pypdf` (`app/extraction.py`), not
  pre-baked JSON pretending to be documents.
- **Storage**: SQLite (`onboarding.db`). Two tables — `runs` (full trace of
  every submission, backs the Ledger) and `vendor_ledger` (one row per
  decided vendor, used to catch duplicate bank accounts and recognize
  returning vendors).
- **Live run view**: the `/api/submissions/stream` and
  `/api/demo-scenarios/{key}/stream` endpoints are genuine Server-Sent
  Event streams — each stage is computed for real and pushed to the
  browser the moment it completes (not a pre-recorded animation).
- **Frontend**: a single static HTML/CSS/JS file (`frontend/index.html`),
  no build step, so "run it" really does mean one command.

## Try it without typing anything

The **Submit** page has nine one-click scenario buttons — happy path, six
edge cases, and two "seed" runs needed to set up history for the
duplicate-account and returning-vendor cases. Run `seed_vantage` before
`edge_duplicate_bank_account`, and `seed_anchor` before
`edge_returning_vendor_expired_doc` (the buttons are ordered this way on
the page).

You can also fill out the manual form and attach your own PDFs — the
sample-doc PDFs in `backend/sample_data/docs/` are good starting points to
edit if you want to construct a new scenario.

## The pipeline (7 stages, in order)

1. **Intake & schema validation** — required fields present, email/phone
   well-formed.
2. **Document validation** — all three PDFs present and machine-readable.
3. **Field extraction** — pulls company name, registration number, tax ID,
   country, account holder, account number, bank name, and SWIFT/BIC out
   of the actual PDF text.
4. **Cross-document consistency check** — every field extracted from every
   document is compared against what was typed on the form, not just
   company names (full table below).
5. **Tax ID & bank country consistency** — does the tax ID's format
   actually match the declared country (checked positively, by
   pattern-matching known formats, not just "looks weird")?
6. **Risk & vendor history check** — duplicate bank account reuse under a
   different name, returning-vendor recognition, soft signals like a
   personal email domain.
7. **Decision** — synthesizes everything into one verdict.

## Stage 4 in detail — what gets cross-checked, and how

| Document | Field | Compared to | Match type |
|---|---|---|---|
| Registration cert | Company name | Submitted legal name | Fuzzy (legal suffixes stripped) |
| Registration cert | Registration number | Submitted registration number | Exact (formatting-normalized) |
| Registration cert | Country of incorporation | Submitted country | Alias-normalized exact |
| Tax cert | Company name | Submitted legal name | Fuzzy |
| Tax cert | Tax ID | Submitted tax ID | Exact (formatting-normalized) |
| Tax cert | Country | Submitted country | Alias-normalized exact |
| Bank letter | Account holder name | Submitted name (or trading name) | Fuzzy |
| Bank letter | Account number | Submitted bank account number | Exact (formatting-normalized) |
| Bank letter | Bank name | Submitted bank name | Fuzzy |
| Bank letter | SWIFT/BIC | Submitted SWIFT/BIC | Exact (formatting-normalized) |

Two deliberately different comparison strategies:

- **Exact identifiers** (registration number, tax ID, account number,
  SWIFT/BIC) are normalized (spaces/dashes stripped, uppercased) and then
  required to match *exactly*. No fuzzy similarity here — a single
  transposed digit in an account number is a real, meaningful difference,
  not a formatting quirk.
- **Names and countries** use fuzzy matching or alias normalization,
  because "Acme Supplies Ltd" vs "Acme Supplies LLC" or "USA" vs "United
  States" are the same thing written two ways.

Severity is **not uniform** across this stage — see the edge case table
below for why a document issued to the wrong company is treated completely
differently from a typo'd account number.

## The edge cases, and why they're not trivial

The interesting part of this problem isn't detecting *that* something is
inconsistent — it's deciding **how severely to treat each kind of
inconsistency**, because treating every anomaly the same way is exactly
what makes real procurement review bad (either too strict, and legitimate
vendors get bounced for no reason, or too loose, and fraud gets through).

| Scenario | What's unusual | Verdict | Why |
|---|---|---|---|
| **"Bluewave" with Meridian's certs** | Registration and tax certificates are issued to a completely different company than the one applying | **Rejected** | A registration/tax certificate is issued to one specific legal entity — there's no legitimate reason it would belong to someone else. Treated as a hard stop (wrong upload or attempted identity misuse), not a request for clarification. |
| **Bluewave, account number typo** | The bank account number typed on the form doesn't match the number printed on Bluewave's own (correct) bank letter | **Pending** | Unlike a wrong company's documents, a mismatched account number is a very plausible honest typo — a single transposed digit in a 12-digit number is not a fraud signal on its own. Ask the vendor to confirm rather than reject. |
| **Nimbus Retail** | Bank account is held by the parent company, not the applicant | **Pending** | A name mismatch alone has too many legitimate explanations (subsidiaries, holding companies, factoring agents) to auto-reject. We ask for a one-line clarification instead of guessing or blocking. Adding a `relationship_note` explaining it clears this check entirely. |
| **Meridian Traders** | Declares "United States" but the tax ID is *shaped* like a UK VAT number | **Rejected** | Unlike a fuzzy name mismatch, this is a positive, provable inconsistency — there's no benign reason a US tax ID would be formatted like a UK one. Treated as a fabrication signal, not a typo. |
| **Sterling Freight Partners** | Submits a bank account number that's already on file for a *different* company (Vantage Freight Co) | **Rejected**, overrides everything else | This is the classic payment-redirection fraud pattern. Even though Sterling's own documents are internally consistent, reusing someone else's payout account is disqualifying on its own — it doesn't matter how clean the rest of the submission looks. |
| **Anchor Supplies (renewal)** | A previously-approved vendor resubmits with one expired tax certificate | **Pending**, lightweight | We recognize this vendor from history and don't re-run a full suspicious-until-proven review — the message asks for exactly the one thing that's actually missing, not a generic "please resubmit everything." |

The decision priority (hard fraud signals > wrong-entity documents > missing
info > typo-prone field mismatches > soft signals) is implemented explicitly
and commented in `app/engine.py` — that ordering *is* the judgment call this
exercise is testing, so it's kept visible rather than buried in a scoring
formula.

## Decision priority, in full (most severe first)

1. Duplicate bank account reuse under a different company name → **Rejected**, overrides everything else.
2. Tax ID format provably matches a different country than declared → **Rejected**.
3. Registration or tax certificate issued to a different company entirely → **Rejected**.
4. Missing required fields or unreadable documents → **Pending**.
5. Returning vendor (prior approval on file) with only one expired document → **Pending**, lightweight.
6. Name mismatches (bank holder) or any other field mismatch (registration number, tax ID, account number, SWIFT/BIC, country, bank name) → **Pending**, specific ask.
7. Only soft signals remain (e.g. personal email domain) → **Approved**, noted.
8. Nothing flagged → **Approved**.

## Assumptions made (noted per the case study's guidance to state them)

- Three documents are treated as required for a complete submission:
  registration certificate, tax certificate, bank confirmation letter.
- Tax ID format validation covers US, UK, Germany, India, Singapore, and
  UAE as a representative sample — not exhaustive, but enough to
  demonstrate the mechanism (adding a country is a one-line regex in
  `app/rules.py`).
- Country name comparisons normalize a small set of common aliases (USA/
  U.S./America → "united states", UK/U.K./Great Britain → "united
  kingdom") — not exhaustive, but enough to avoid false positives from
  obvious formatting differences.
- "Duplicate bank account" and other exact-identifier checks are compared
  after stripping spaces and dashes and uppercasing — not a full
  IBAN-aware normalization, but enough to catch formatting noise without
  false negatives.
- A vendor-provided `relationship_note` is treated as sufficient
  explanation for a moderate bank-holder name mismatch (e.g. "banking
  handled by our parent, Acme Holdings") — it downgrades that check from a
  blocking warning to a passed, but still logged, note. A real system
  might also want to verify the note against a document.

## AI usage

The rules engine itself is deterministic on purpose — every check is a
regex, a similarity score, or a database lookup, so I can defend exactly
why any given verdict came out the way it did in the interview. The one
place I use an LLM (optionally) is polishing the vendor-facing message in
`app/messaging.py`: the rules engine decides *what* to say deterministically,
and Claude (if an API key is set) is only asked to make the wording
friendlier — with a plain-template fallback so a missing key or network
hiccup never breaks the live demo.

## Project structure

```
backend/
  app/
    main.py        FastAPI app, SSE streaming endpoints, dashboard API
    engine.py       Pipeline orchestrator + decision synthesis
    rules.py        Name matching, ID/country normalization, tax ID formats, email checks
    extraction.py   PDF text extraction + field parsing
    messaging.py    Vendor message generation (template + optional Claude polish)
    models.py       Pydantic schemas
    db.py           SQLite persistence (runs + vendor ledger)
  sample_data/
    make_pdfs.py    Generates all sample PDF documents
    scenarios.py    Defines the 9 demo scenarios
    run_scenarios.py  Regression test: runs all scenarios, checks verdicts
frontend/
  index.html        Submit / Live Run / Ledger — single file, no build step
```

## Regression check

```bash
cd backend
python3 sample_data/run_scenarios.py
```

Runs all 9 scenarios directly against the engine (no server needed) and
prints PASS/FAIL against the expected verdict for each — useful any time
you tweak a rule.
