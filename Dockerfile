FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Copy app files
COPY backend.py ./
COPY MFV130Gen.csv ./
COPY static ./static
# Expose port and start uvicorn. On Render the service provides the port in the $PORT env var,
# so use it if present, otherwise default to 8000 for local development.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend:app --host 0.0.0.0 --port ${PORT:-8000}"]
