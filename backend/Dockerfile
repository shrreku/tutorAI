FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for:
# - gcc/libpq-dev: PostgreSQL driver compilation
# - libgl1/libglib2.0-0: OpenCV headless (used by Docling for image processing)
# - tesseract-ocr: OCR engine for Docling (default fallback)
# - poppler-utils: PDF rendering utilities used by Docling
# - libmagic1: file type detection
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    poppler-utils \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
