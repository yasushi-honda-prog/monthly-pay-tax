"""過去の業務報告データから活動分類・業務分類の使用状況を分析"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from google.cloud import bigquery

client = bigquery.Client(project='monthly-pay-tax')
query = """
SELECT activity_category, work_category, COUNT(*) as cnt
FROM `monthly-pay-tax.pay_reports.gyomu_reports`
WHERE activity_category IS NOT NULL AND activity_category != ''
GROUP BY activity_category, work_category
ORDER BY activity_category, cnt DESC
"""
results = client.query(query).result()
for row in results:
    print(f"{row.activity_category}|{row.work_category or ''}|{row.cnt}")
