FROM python:3.11-slim

WORKDIR /app

# CPU torch first (avoids multi-GB CUDA wheels), then the rest
COPY requirements.txt .
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

# generate the synthetic demo scene at build time so the container demos offline
RUN python scripts/make_synthetic_video.py

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
