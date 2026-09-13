FROM python:3.12-slim

RUN pip install --no-cache-dir grocy-mcp fastapi uvicorn python-multipart

CMD ["grocy-mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000", "--path", "/mcp"]
