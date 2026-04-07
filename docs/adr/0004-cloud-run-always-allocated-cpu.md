# ADR 0004: pay-dashboard の Cloud Run CPU を instance-based (always-allocated) に切替

## ステータス
採用 (2026-04-07)

## 背景
pay-dashboard の月コストが 1月¥15 → 3月¥6,961 と増加傾向（ユーザー報告ベース）。BigQueryが原因と推測したが、`INFORMATION_SCHEMA.JOBS` 実測の結果、BQは月¥12（全体の0.1%）で無罪と判明。

Cloud Billing Reportsで真犯人を確定:
- 3月の主犯: **Cloud Run "Services CPU (Request-based billing)" ¥4,536（92%）**
- 使用量: 1,384,757 vCPU秒 ≈ 385 vCPU時間/月
- 営業22日 × 8時間で割ると **平均2.2 vCPU並列** ≈ 同時接続2-3人が業務時間中常時接続

アクセスログ（`/_stcore/stream`）調査でボット攻撃を否定:
- 接続元IPは全て国内（NTT東/西、OCN、ソフトバンク）
- User-Agentは全てChrome 146（Mac/Windows）
- 同一IPから5分間隔（Streamlit WebSocket reconnectと一致）

→ 真因は**正規ユーザーがブラウザを業務時間中開きっぱなし**にすることで、Streamlit WebSocketが常時接続維持され、Cloud Runが常時「処理中」扱いになりCPU秒数が積算する構造的問題。

## 検討した選択肢
| 案 | 評価 | 不採用理由 |
|---|---|---|
| BQキャッシュ強化・VIEWマテリアライズ | ❌ | BQ月¥12のため効果ゼロ |
| Cloud Armor / Caddy reverse proxy | ❌ | ボット攻撃の証拠なし |
| Cloud Run timeout短縮（300s→さらに短く） | ❌ | 既に300s適用済み、Streamlit JSが自動再接続するため効果なし |
| CPU 0.5 vCPU化 | ❌ | Cloud Run制約: concurrency>1 では CPU<1 不可 |
| **`--no-cpu-throttling`（instance-based切替）** | ⭕ | **採用**: 単価-25%、リスクなし、切戻し1コマンド |
| Streamlit fragment idle timeout（PR） | △ | 効果未検証、コード変更要、まずは設定変更で効果測定 |
| Looker Studioへ部分移行 | △ | 中長期の本命だが今は過剰投資 |

## 決定
pay-dashboard を **instance-based CPU billing** に切替、加えて max-instances を暴走防止のため絞る。

```bash
gcloud run services update pay-dashboard \
  --region=asia-northeast1 \
  --no-cpu-throttling \
  --max-instances=3
```

最終構成:
- CPU: 1 vCPU（変更なし）
- Memory: 512Mi（変更なし）
- min-instances: 0（変更なし）
- max-instances: 20 → **3**
- timeout: 300s（変更なし）
- cpu-throttling: true → **false**

## 期待される効果
- vCPU単価: $0.000024 → $0.000018（**-25%**）
- Memory単価: $0.0000025 → $0.000002（-20%）
- 月コスト見込み: 3月¥4,536 → **約¥3,400**（年¥13,200削減）

## 切戻しコマンド
```bash
gcloud run services update pay-dashboard \
  --region=asia-northeast1 \
  --cpu-throttling \
  --max-instances=20
```

## 検証手順
1. デプロイ後 `curl -I https://pay-dashboard-209715990891.asia-northeast1.run.app/` で HTTP 200 確認（実施済み: 94ms応答）
2. **3〜5日後にCloud Billing Reportsで日次コスト確認**（日次¥95前後に収まるか）
3. 1週間後に効果測定、不十分なら追加対策（Streamlit fragment idle timeout / Looker Studio分離）を検討

## 残課題
- **ユーザー報告 ¥10,079 と Reports ¥4,903 のズレが未解明**: 請求書PDF確認で「請求書≠使用月（前月分が翌月請求）」かを確定する必要あり
- **予算アラート未設定**: 月¥3,000閾値で 50/90/100% 通知をフォロータスクとして起票候補

## 関連
- 調査コマンド（再現用）:
  ```bash
  # BQ実スキャン量
  bq query --use_legacy_sql=false 'SELECT DATE(creation_time) AS day, ROUND(SUM(total_bytes_billed)/POW(10,9),3) AS gb_billed FROM `monthly-pay-tax`.`region-asia-northeast1`.INFORMATION_SCHEMA.JOBS WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY) AND job_type="QUERY" GROUP BY day ORDER BY day DESC'

  # Streamlit WebSocketアクセスログ
  gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="pay-dashboard" AND httpRequest.requestUrl=~"_stcore/stream"' --freshness=7d --format="value(httpRequest.remoteIp,httpRequest.userAgent)" | sort -u
  ```
- 参考: [Why Streamlit + Cloud Run is a Billing Trap (DEV.to)](https://dev.to/pascal_cescato_692b7a8a20/how-i-cut-my-cloud-run-bill-by-96-by-stopping-a-polish-botnet-5ak) — 今回はボット攻撃ではなかったが、診断アプローチとして参考
