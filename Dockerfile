FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fin \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir grocy-mcp fastapi uvicorn python-multipart recipe-scrapers pytesseract Pillow

CMD ["grocy-mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000", "--path", "/mcp"]
