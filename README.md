# CV Analyzer (CvFit)

## Overview
CvFit is a full-stack FastAPI + Kubernetes application that analyzes a CV (PDF/DOCX/TXT) against a given job description.  
It provides:
- **Fit Score**: How well the CV matches the job description
- **Improvement Suggestions**: Skills or experience to add or highlight
- **Expected Salary Note**: Market-based salary guidance for IL market

---

## Phases Completed

### Phase 0 – Initial Setup
- Installed **minikube**, **kubectl**, **docker** on macOS with Apple Silicon.
- Created the Python FastAPI skeleton (`main.py`).
- Built initial API endpoints for `/analyze` and `/health`.
- Configured `requirements.txt` with key dependencies: fastapi, uvicorn, pydantic, python-multipart, pdfplumber, rapidfuzz.

### Phase 1 – Containerization
- Wrote a production-grade Dockerfile with multi-stage build (python:3.11-slim).
- Built Docker image: `docker build -t cv-analyzer:local .`
- Tested container locally via `docker run`.
- Added `.dockerignore`.

### Phase 2 – Kubernetes Deployment
- Installed and started minikube with Docker driver.
- Created Kubernetes manifests:
  - `deployment.yaml` (FastAPI pod)
  - `service.yaml` (ClusterIP service)
- Verified deployment with `kubectl get pods` and `kubectl get svc`.
- Exposed service locally with `minikube service cv-analyzer-service -n default`.

### Phase 3 – API Enhancement
- Added PDF/DOCX/TXT parsing (pypdf, python-docx).
- Implemented structured response model with pydantic.
- Added better error handling for empty files or invalid formats.

### Phase 4 – Kubernetes Secrets
- Created a Kubernetes secret for storing the OpenAI API key:
  ```bash
  kubectl create secret generic openai-secret -n default --from-literal=OPENAI_API_KEY="sk-..."
  ```
- Updated deployment to pull the key from `env`:
  ```yaml
  env:
  - name: OPENAI_API_KEY
    valueFrom:
      secretKeyRef:
        name: openai-secret
        key: OPENAI_API_KEY
  ```

### Phase 5 – Continuous Build & Rollout
- Adopted a tagging strategy with `TAG=$(date +%s)` for each new build:
  ```bash
  docker build --no-cache -t cv-analyzer:$TAG .
  minikube image load cv-analyzer:$TAG
  kubectl set image deployment/cv-analyzer cv-analyzer=cv-analyzer:$TAG -n default
  kubectl rollout status deployment cv-analyzer -n default
  ```
- Verified pod uses correct image:
  ```bash
  kubectl get deploy cv-analyzer -n default -o jsonpath='{.spec.template.spec.containers[0].image}'
  ```

### Phase 6 – AI Enhancements & Frontend
- Integrated **OpenAI SDK** (openai==1.51.2).
- Added `gpt-4o-mini` model for analysis.
- Implemented HTML frontend using Jinja2 templates and TailwindCSS-style UI for interactive upload and live results.

---

## Command Reference (Key Commands)

| Action | Command |
|--------|--------|
| Build & Tag Image | `TAG=$(date +%s) && docker build --no-cache -t cv-analyzer:$TAG .` |
| Load Image to Minikube | `minikube image load cv-analyzer:$TAG` |
| Update Deployment | `kubectl set image deployment/cv-analyzer cv-analyzer=cv-analyzer:$TAG -n default` |
| Monitor Rollout | `kubectl rollout status deployment cv-analyzer -n default` |
| View Logs | `kubectl logs -f deploy/cv-analyzer -n default` |
| Exec Into Pod | `kubectl exec -it deploy/cv-analyzer -n default -- sh` |
| Port-forward Service | `minikube service cv-analyzer-service -n default` |

---

## Deployment Verification
- Check environment variable inside pod:
  ```bash
  kubectl exec -it deploy/cv-analyzer -n default -- printenv | grep OPENAI
  ```
- Test direct OpenAI API connectivity:
  ```bash
  curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
  ```
- Ensure running version:
  ```bash
  kubectl get deploy cv-analyzer -n default -o jsonpath='{.spec.template.spec.containers[0].image}'
  ```

---

## Frontend
The `templates/index.html` UI provides:
- CV file upload field (.pdf, .docx, .txt)
- Job description text area
- "Analyze" button that triggers API call
- Beautiful output with fit score bar, expected salary, and actionable suggestions

---

## How to Run
```bash
# Local dev server (optional)
uvicorn main:app --reload

# or using Kubernetes
minikube start
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
minikube service cv-analyzer-service -n default
```

---

## Next Steps
- Add authentication for private deployments.
- Support multilingual CV analysis.
- Integrate database for storing historical analyses.

---

## License
MIT
