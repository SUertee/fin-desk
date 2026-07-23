FROM python:3.12-slim

RUN useradd -m -u 1000 app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/statement-inbox /data/statement-imports \
    && chown -R app:app /app /data
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
