"""共有BigQueryクライアント"""

import streamlit as st
from google.cloud import bigquery

from lib.constants import PROJECT_ID


@st.cache_resource
def get_bq_client():
    return bigquery.Client(project=PROJECT_ID)


@st.cache_data(ttl=3600)
def load_data(query: str):
    client = get_bq_client()
    return client.query(query).to_dataframe()
