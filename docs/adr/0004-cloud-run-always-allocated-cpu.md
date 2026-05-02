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

## 効果測定 (2026-05-03、Issue #94)

観測期間: 2026-04-02 〜 2026-05-02 (30日 / ADR-0004 適用日 2026-04-07 をまたぐ)
データソース: Cloud Monitoring API (`run.googleapis.com/container/billable_instance_time`, `request_count`)

⚠️ 制約: BQ Billing export 未設定 + `yasushi-honda@tadakayo.jp` に課金アカウント `013C90-D4C0A0-A391D6` の billing.viewer 権限なし → 実コストではなく公開単価ベースの**理論値**で評価。

### 利用量（30日合計）

| サービス | billable_instance_time | request_count | vCPU | Memory |
|---------|------------------------|---------------|------|--------|
| pay-collector | 43,612 s (12.1 h) | 41 | 1 | 2 GiB |
| pay-dashboard | 1,318,471 s (366.2 h) | 23,588 | 1 | 0.5 GiB |

### 週次推移（pay-dashboard, billable_instance_time）

| 週末日 | 時間 | 備考 |
|-------|------|------|
| 2026-04-05 | 63.8 h | 適用前期間を含む |
| 2026-04-12 | 86.3 h | 適用後 1週目 |
| 2026-04-19 | 102.5 h | 適用後 2週目（ピーク） |
| 2026-04-26 | 80.9 h | 適用後 3週目 |
| 2026-05-03 | 72.3 h | 適用後 4週目 |

適用後 4週平均: 約 85.5 h / 週

### 理論コスト（asia-northeast1 Tier 1, always-allocated 単価）

公開単価: vCPU $0.000018/s、Memory $0.000002/GiB-s、Requests $0.40/M

| サービス | vCPU | Memory | Requests | 合計 (USD) | 合計 (¥, $1=¥150) |
|---------|------|--------|----------|------------|-------------------|
| pay-collector | $0.785 | $0.174 | $0.00002 | $0.96 | ¥144 |
| pay-dashboard | $23.73 | $1.32 | $0.0094 | $25.07 | ¥3,761 |
| **合計** | | | | **$26.03** | **¥3,905** |

### 評価

- ADR-0004 適用前 (3月実績): pay-dashboard ¥4,536
- 適用後 (本観測): pay-dashboard ¥3,761（理論値）
- → **17% 削減**は確認できるが、ADR-0004 期待値 ¥3,400 を **+11% 超過**
- 月¥3,000 閾値に対しては **+25% 超過**（dashboard 単体で予算超）

差異要因の仮説:
- WebSocket 持続による idle 時間の課金（業務時間外も接続が続く可能性）
- Streamlit 同時セッション数の振れ（max=3 で複数インスタンス並走時間）
- CI/CD（GitHub Actions）デプロイによるリビジョン切替時の一時的ダブル課金

### 判定: ⭕ 採用継続（コスト改善は確認、ただし期待を下回る）

## 残課題
- **ユーザー報告 ¥10,079 と Reports ¥4,903 のズレが未解明**: 請求書PDF確認で「請求書≠使用月（前月分が翌月請求）」かを確定する必要あり
- **予算アラート未設定**: 月¥3,000閾値は実測超過のため、設定値を ¥4,500 程度に上方修正検討。設定には課金アカウント `013C90-D4C0A0-A391D6` への billing.admin 権限取得が必要（現状 `yasushi-honda@tadakayo.jp` には未付与、`billingbudgets.googleapis.com` API も未有効）
- **BQ Billing export 未設定**: 将来の実コスト分析のため `monthly-pay-tax:billing_export` データセット作成 + Billing → BQ export 設定を推奨。billing.admin 権限取得後に対応
- **ユーザー WebSocket 持続による idle 課金**: dashboard アクセスログで業務時間外接続の頻度を測定し、必要なら Streamlit 側の auto-disconnect / idle timeout 検討

## 関連
- 調査コマンド（再現用）:
  ```bash
  # BQ実スキャン量
  bq query --use_legacy_sql=false 'SELECT DATE(creation_time) AS day, ROUND(SUM(total_bytes_billed)/POW(10,9),3) AS gb_billed FROM `monthly-pay-tax`.`region-asia-northeast1`.INFORMATION_SCHEMA.JOBS WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY) AND job_type="QUERY" GROUP BY day ORDER BY day DESC'

  # Streamlit WebSocketアクセスログ
  gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="pay-dashboard" AND httpRequest.requestUrl=~"_stcore/stream"' --freshness=7d --format="value(httpRequest.remoteIp,httpRequest.userAgent)" | sort -u
  ```
- 参考: [Why Streamlit + Cloud Run is a Billing Trap (DEV.to)](https://dev.to/pascal_cescato_692b7a8a20/how-i-cut-my-cloud-run-bill-by-96-by-stopping-a-polish-botnet-5ak) — 今回はボット攻撃ではなかったが、診断アプローチとして参考
