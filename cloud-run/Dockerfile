FROM python:3.12-slim

ENV PYTHONUNBUFFERED=True
ENV APP_HOME=/app
WORKDIR $APP_HOME

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# PR-C: threads 1 → 2 に増加。POST /eval/team-monthly が sync で 12-20 分
# ブロックする間も health check / dashboard 手動同期が受付可能になる。
# extract_actor は thread-safe (リクエスト毎に google.auth Request を生成、PR-C)。
CMD exec gunicorn --bind :$PORT --workers 1 --threads 2 --timeout 1800 main:app
