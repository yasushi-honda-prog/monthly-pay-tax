FROM python:3.12-slim

ENV PYTHONUNBUFFERED=True
ENV APP_HOME=/app
WORKDIR $APP_HOME

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 日本語フォント（支払明細書PDF生成用）
RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

# Google翻訳を無効化: StreamlitのHTMLテンプレートにtranslate="no"を埋め込む
RUN sed -i 's|<html|<html translate="no" lang="ja"|' \
    /usr/local/lib/python3.12/site-packages/streamlit/static/index.html

COPY . .

CMD exec streamlit run app.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
