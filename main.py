from __future__ import annotations

import io
import json
import logging
import os
import re
import time
from typing import List, Optional

from docx import Document as DocxDocument
from fastapi import (
    BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings
from pypdf import PdfReader
from tenacity import retry, stop_after_attempt, wait_exponential

# ------------------------------------------------------------------------------
# Settings & Config
# ------------------------------------------------------------------------------

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    MODEL_NAME: str = "gpt-4o-mini"
    MAX_FILE_SIZE_MB: int = 8
    CORS_ALLOW_ORIGINS: str = "*"  # comma-separated or "*"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()  # will raise if OPENAI_API_KEY is missing
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# ------------------------------------------------------------------------------
# App & Middleware
# ------------------------------------------------------------------------------

app = FastAPI(title="CV Analyzer API", version="0.2.0")
origins = (
    ["*"] if settings.CORS_ALLOW_ORIGINS.strip() == "*"
    else [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",")]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static + templates (optional – safe to keep)
try:
    templates = Jinja2Templates(directory="templates")
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    # If folders do not exist, ignore: API still works.
    pass

# ------------------------------------------------------------------------------
# Simple in-memory rate limit (per-process, best-effort)
# ------------------------------------------------------------------------------

_LAST_CALL_TS: float = 0.0
_MIN_INTERVAL_SEC = 0.5  # ~2 rps per pod

def rate_limit():
    global _LAST_CALL_TS
    now = time.time()
    if now - _LAST_CALL_TS < _MIN_INTERVAL_SEC:
        raise HTTPException(status_code=429, detail="Too many requests; please slow down.")
    _LAST_CALL_TS = now

# ------------------------------------------------------------------------------
# Models (I/O)
# ------------------------------------------------------------------------------

class AnalyzeResponse(BaseModel):
    improvement_suggestions: List[str]
    fit_score: int = Field(ge=0, le=100)
    fit_reason: str
    expected_salary_note: str

class ExtractResponse(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    years_experience: Optional[str] = None
    skills: List[str] = []
    education: List[str] = []
    certifications: List[str] = []
    summary: Optional[str] = None

class BatchAnalyzeItem(BaseModel):
    filename: str
    result: AnalyzeResponse

class BatchAnalyzeResponse(BaseModel):
    job_description: str
    results: List[BatchAnalyzeItem]

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _bytes_to_mb(n: int) -> float:
    return round(n / (1024 * 1024), 2)

def _ensure_size(upload: UploadFile):
    # read() may load entire file; we peek then restore
    pos = upload.file.tell()
    upload.file.seek(0, os.SEEK_END)
    size = upload.file.tell()
    upload.file.seek(pos)
    if size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {_bytes_to_mb(size)} MB (max {settings.MAX_FILE_SIZE_MB} MB).",
        )

def _read_file_content(upload: UploadFile) -> str:
    _ensure_size(upload)
    content = upload.file.read()
    upload.file.seek(0)
    name = (upload.filename or "").lower()

    if name.endswith(".txt"):
        return content.decode(errors="ignore")

    if name.endswith(".docx"):
        with io.BytesIO(content) as bio:
            doc = DocxDocument(bio)
            return "\n".join(p.text for p in doc.paragraphs)

    if name.endswith(".pdf"):
        text = []
        with io.BytesIO(content) as bio:
            reader = PdfReader(bio)
            for page in reader.pages:
                text.append(page.extract_text() or "")
        return "\n".join(text)

    # Fallback: try decode as text
    try:
        return content.decode(errors="ignore")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Use .pdf, .docx, or .txt",
        )

def _build_analysis_prompt(cv_text: str, jd_text: str) -> str:
    return f"""
You are an expert technical recruiter and hiring manager. Analyze the candidate CV against the job description.

Return ONLY a JSON object with these keys and types:
- improvement_suggestions: string[] (3-8 bullets, concise)
- fit_score: number (0-100)
- fit_reason: string
- expected_salary_note: string

CV:
\"\"\"{cv_text}\"\"\"

JOB DESCRIPTION:
\"\"\"{jd_text}\"\"\"

Be factual and specific; avoid hallucinations. Keep salary note for Israel (gross/month) as a broad range when uncertain.
"""

def _build_extract_prompt(cv_text: str) -> str:
    return f"""
Extract structured information from the following CV.
Return ONLY a JSON object with keys:
- name (string|null)
- email (string|null)
- phone (string|null)
- location (string|null)
- years_experience (string|null)
- skills (string[])
- education (string[])
- certifications (string[])
- summary (string|null)

CV:
\"\"\"{cv_text}\"\"\"
"""

@retry(wait=wait_exponential(min=1, max=8), stop=stop_after_attempt(3))
def _chat_json(prompt: str) -> dict:
    """
    Call OpenAI with JSON mode enforced (1.x SDK).
    Retries transient errors with exponential backoff.
    """
    resp = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
        max_tokens=900,
    )
    raw = (resp.choices[0].message.content or "").strip()
    return json.loads(raw)

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "model": settings.MODEL_NAME}

# Optional: keep home if you render a UI via Jinja
@app.get("/")
def home(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception:
        return JSONResponse({"status": "ok", "message": "API root"}, 200)

@app.get("/models")
def list_models():
    """Quick sanity-check that the API key works and list model ids."""
    try:
        data = client.models.list()
        ids = [m.id for m in data.data] if getattr(data, "data", None) else []
        return {"count": len(ids), "models": ids[:50]}  # limit response
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

@app.post("/extract", response_model=ExtractResponse, dependencies=[Depends(rate_limit)])
async def extract(cv_file: UploadFile = File(..., description="Resume file (.pdf/.docx/.txt)")):
    text = _read_file_content(cv_file)[:120_000]
    try:
        data = _chat_json(_build_extract_prompt(text))
        # Validate shape against Pydantic
        return ExtractResponse(**data)
    except ValidationError as ve:
        raise HTTPException(status_code=500, detail=f"Invalid JSON fields: {ve}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

@app.post("/analyze", response_model=AnalyzeResponse, dependencies=[Depends(rate_limit)])
async def analyze(
    cv_file: UploadFile = File(..., description="Resume (.pdf/.docx/.txt)"),
    job_description: str = Form(..., description="Paste the JD text")
):
    cv_text = _read_file_content(cv_file)
    prompt = _build_analysis_prompt(cv_text=cv_text[:120_000], jd_text=job_description[:60_000])

    try:
        data = _chat_json(prompt)
        return AnalyzeResponse(**data)
    except ValidationError as ve:
        raise HTTPException(status_code=500, detail=f"Invalid JSON fields: {ve}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

@app.post("/analyze/batch", response_model=BatchAnalyzeResponse, dependencies=[Depends(rate_limit)])
async def analyze_batch(
    files: List[UploadFile] = File(..., description="Multiple CV files"),
    job_description: str = Form(..., description="JD text applied to each CV")
):
    jd = job_description[:60_000]
    results: List[BatchAnalyzeItem] = []

    for f in files:
        try:
            cv_text = _read_file_content(f)[:120_000]
            data = _chat_json(_build_analysis_prompt(cv_text, jd))
            item = BatchAnalyzeItem(filename=f.filename or "cv", result=AnalyzeResponse(**data))
            results.append(item)
        except Exception as e:
            # include a "failed" record instead of aborting entire batch
            failed = AnalyzeResponse(
                improvement_suggestions=["Processing failed."],
                fit_score=0,
                fit_reason=f"Error: {e}",
                expected_salary_note="N/A",
            )
            results.append(BatchAnalyzeItem(filename=f.filename or "cv", result=failed))

    return BatchAnalyzeResponse(job_description=job_description, results=results)