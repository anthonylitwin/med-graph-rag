FROM python:3.11-slim

WORKDIR /app

COPY apps/api/requirements.txt .
COPY requirements-local-models.txt .

RUN pip install --no-cache-dir -r requirements.txt -r requirements-local-models.txt

COPY apps/api/app ./app
COPY packages ./packages
COPY pipelines ./pipelines
COPY scripts ./scripts
COPY data ./data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
