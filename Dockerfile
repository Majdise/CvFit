# Python base (works on Apple Silicon + Intel)
FROM python:3.11-slim

# Make logs flush immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps (build & runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential && \
    rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Copy only requirements first (better caching)
COPY requirements.txt /app/

# Install deps
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the app
COPY . /app

# Expose FastAPI port
EXPOSE 8000

# Start server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]