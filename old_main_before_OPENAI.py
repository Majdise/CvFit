from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import io
import pdfplumber
from rapidfuzz import fuzz, process

app = FastAPI(title="CV Analyzer API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisResponse(BaseModel):
    fit_score: int
    highlights: list[str]
    gaps: list[str]
    salary_range: str
    suggestions: list[str]

@app.get("/health")
def health():
    return {"status": "ok"}

def extract_pdf_text(file_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
    return "\n".join(text_parts)

def keyword_score(cv_text: str, wanted: list[str], nice: list[str]) -> tuple[int, list[str], list[str]]:
    cv_lower = cv_text.lower()
    hits, gaps = [], []
    score = 0

    def hit(k, points=10):
        nonlocal score; score += points; hits.append(k)

    # “hard” skills you want to see
    for k in wanted:
        if k in cv_lower:
            hit(k)
        else:
            gaps.append(k)

    # “nice to have”
    for k in nice:
        if k in cv_lower:
            hit(k, points=4)

    # light fuzzy bonus for job title similarity
    title_candidates = ["technical support", "support engineer", "site reliability",
                        "devops", "data engineer", "qa", "customer success"]
    best = process.extractOne(cv_lower[:2000], title_candidates, scorer=fuzz.partial_ratio)
    if best and best[1] >= 80:
        score += 6
        hits.append(f"role match: {best[0]}")

    score = max(0, min(100, score))
    return score, hits, gaps

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    job_description: str = Form(...),
    cv_file: UploadFile = File(...)
):
    file_bytes = await cv_file.read()
    cv_text = extract_pdf_text(file_bytes)

    # very simple signal extraction from JD for now
    jd_lower = job_description.lower()
    wanted = []
    nice = []

    def req_if(*keys): wanted.extend([k for k in keys if k not in wanted])
    def nice_if(*keys): nice.extend([k for k in keys if k not in nice])

    # heuristics from JD
    if "sql" in jd_lower: req_if("sql")
    if "rest" in jd_lower or "api" in jd_lower: req_if("api", "rest")
    if "linux" in jd_lower: req_if("linux")
    if "aws" in jd_lower: nice_if("aws")
    if "grafana" in jd_lower or "opensearch" in jd_lower: nice_if("grafana", "opensearch")
    if "python" in jd_lower or "bash" in jd_lower: nice_if("python", "bash")
    if "kubernetes" in jd_lower: nice_if("kubernetes")
    if "support" in jd_lower: req_if("support")

    fit, hits, missing = keyword_score(cv_text, wanted, nice)

    suggestions = []
    if "sql" in missing:
        suggestions.append("Add a bullet with SQL: queries you ran, logs you analyzed, or metrics you computed.")
    if "api" in missing or "rest" in missing:
        suggestions.append("Mention REST APIs you integrated/troubleshot; include tools and error codes.")
    if "linux" in missing:
        suggestions.append("Show Linux experience (shell, logs, services, systemctl, journalctl).")
    if "support" in missing:
        suggestions.append("Quantify support impact (tickets/week, SLA, MTTR, escalations handled).")

    # demo salary rule of thumb (Israel, junior-mid tech support / data / ops) – adjust later
    salary = "₪17K–₪23K gross (rough guide; adjust by seniority/company)."

    # convert “missing” to readable gaps
    gap_msgs = [f"Missing signal for: {m}" for m in missing]

    return AnalysisResponse(
        fit_score=fit,
        highlights=[f"Found: {h}" for h in hits][:6],
        gaps=gap_msgs[:6],
        salary_range=salary,
        suggestions=suggestions[:6] or ["Looks good—tighten bullets with numbers and outcomes."]
    )