FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ml_inference /app/ml_inference
ENV PYTHONPATH=/app
CMD ["uvicorn", "ml_inference.app:app", "--host", "0.0.0.0", "--port", "8001"]
