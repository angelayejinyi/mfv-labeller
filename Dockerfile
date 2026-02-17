FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Copy app files
COPY backend.py ./
COPY MFV130Gen.csv ./
COPY static ./static
# Expose port and start uvicorn
EXPOSE 8000
CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8000"]
