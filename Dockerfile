FROM python:3.12-slim

# Create isolated unprivileged application user
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY api ./api
COPY agent ./agent
COPY llm ./llm
COPY sandbox ./sandbox
COPY evaluation ./evaluation
COPY database ./database
COPY schemas ./schemas
COPY ui ./ui
COPY .env.example .env.example

# Set permissions for unprivileged user
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000 8501

CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
