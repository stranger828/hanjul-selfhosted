FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt && python -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute(\"CREATE VIRTUAL TABLE probe USING fts5(body, tokenize='trigram')\")"
COPY app.py auth.py schema.sql ./
COPY static ./static
COPY scripts ./scripts
RUN mkdir /data /backups && chown 10001:10001 /data /backups
ENV MEMO_HOST=0.0.0.0 PORT=8787 MEMO_DATA_DIR=/data
USER 10001:10001
EXPOSE 8787
CMD ["python", "app.py"]
