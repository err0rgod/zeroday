FROM python:3.11-slim

WORKDIR /app

COPY web/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# Add azure-storage-blob for cloud storage integration
RUN pip install --no-cache-dir azure-storage-blob

COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "web.main:app"]
