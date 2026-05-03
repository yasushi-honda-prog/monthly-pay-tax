FROM python:3.12-slim

ENV PYTHONUNBUFFERED=True
ENV APP_HOME=/app
WORKDIR $APP_HOME

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 日本語フォント（支払明細書PDF生成用）
# fonts-ipafont-gothic: 単体TTFファイル（TTC由来のグリフ文字化けを回避）
RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-ipafont-gothic && \
    rm -rf /var/lib/apt/lists/* && \
    ls /usr/share/fonts/opentype/ipafont-gothic/ipag.ttf > /dev/null

# Google翻訳を無効化: StreamlitのHTMLテンプレートにtranslate="no"を埋め込む
RUN sed -i 's|<html|<html translate="no" lang="ja"|' \
    /usr/local/lib/python3.12/site-packages/streamlit/static/index.html

# Streamlit multipage app の既知挙動 (_stcore/health, _stcore/host-config 404) について
# エンドユーザーが不安にならないようコンソールに先回り説明を出力 (streamlit/streamlit#7074)
RUN sed -i "s|</head>|<script>console.info(\"%c[既知の挙動・無視可] /_stcore/health, /_stcore/host-config の 404 は Streamlit multipage app の既知挙動 (streamlit#7074) で、機能には影響しません。\", \"color:#4a90e2;font-weight:bold\");</script></head>|" \
    /usr/local/lib/python3.12/site-packages/streamlit/static/index.html

COPY . .

CMD exec streamlit run app.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
