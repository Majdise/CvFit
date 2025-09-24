from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
#from typing import Optional
import os
import io
from docx import Document as DocxDocument
from pypdf import PdfReader
from openai import OpenAI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request


app = FastAPI(title="CV Analyzer API")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
# --- Helpers ---
def read_file_content(upload: UploadFile) -> str:
    content = upload.file.read()
    upload.file.seek(0)
    name = upload.filename.lower() if upload.filename else ""

    if name.endswith(".txt"):
        return content.decode(errors="ignore")
    elif name.endswith(".docx"):
        with io.BytesIO(content) as bio:
            doc = DocxDocument(bio)
            return "\n".join(p.text for p in doc.paragraphs)
    elif name.endswith(".pdf"):
        text = []
        with io.BytesIO(content) as bio:
            reader = PdfReader(bio)
            for page in reader.pages:
                text.append(page.extract_text() or "")
        return "\n".join(text)
    else:
        # Fallback: try decode as text
        try:
            return content.decode(errors="ignore")
        except Exception:
            raise HTTPException(status_code=400, detail="Unsupported file type. Use .pdf, .docx, or .txt")

def build_prompt(cv_text: str, jd_text: str) -> str:
    return f"""
You are an expert technical recruiter and hiring manager. Analyze the candidate CV against the job description.

Return JSON with keys: improvement_suggestions (array of bullets), fit_score (0-100), fit_reason (short string), expected_salary_note (short string).

CV:\n{cv_text}\n
JOB DESCRIPTION:\n{jd_text}\n

Rules:
- Be specific and honest. No exaggerations or fabricated claims.
- Focus improvements on skills/keywords the JD actually asks for.
- If the JD mentions tools the candidate didn’t list, suggest adding *only if* they truly used them; otherwise suggest a learning plan.
- Fit score: weigh core reqs (must-haves) heavily; prefer proven, recent experience.
- Expected salary note: give a broad range for IL market (gross/month) based on seniority signals; if ambiguous, say the assumptions.
Output ONLY valid JSON.
"""

class AnalyzeResponse(BaseModel):
    improvement_suggestions: list
    fit_score: int
    fit_reason: str
    expected_salary_note: str

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    cv_file: UploadFile = File(..., description="Your resume as PDF/DOCX/TXT"),
    job_description: str = Form(..., description="Paste the role description text")
):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    cv_text = read_file_content(cv_file)
    if not cv_text.strip():
        raise HTTPException(status_code=400, detail="CV text is empty or unreadable")

    prompt = build_prompt(cv_text=cv_text[:120000], jd_text=job_description[:60000])  # safety truncation

    try:
        client = OpenAI(api_key=api_key)
        # Use a capable reasoning/chat model. If your plan tier supports o4-mini or gpt-4o-mini:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=800
        )
        raw = resp.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

    # Best effort: ensure the reply is valid JSON
    import json, re
    json_str = raw.strip()
    # strip code fences if present
    json_str = re.sub(r"^```json\s*|\s*```$", "", json_str, flags=re.IGNORECASE|re.MULTILINE)

    try:
        data = json.loads(json_str)
        # Pydantic will validate keys/types
        return AnalyzeResponse(**data)
    except Exception as e:
        # fall back with a friendly error
        raise HTTPException(status_code=500, detail=f"Model returned non-JSON or invalid JSON: {e}. Raw: {raw[:400]}")