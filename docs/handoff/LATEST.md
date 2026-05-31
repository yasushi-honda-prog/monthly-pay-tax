# ハンドオフメモ - monthly-pay-tax

**更新日**: 2026-05-31（snapshot 障害対応 + 事後強化完了 — IAM 修正 + 復旧 runbook + Step0 健全性チェック + Step5 fail-safe、PR #153-155 マージ）
**フェーズ**: WAM助成金対応 **技術側完了** + **CI/CD 自動デプロイ稼働中** + **管理機能拡充フェーズ完了** + **運用ドキュメント基盤稼働** + **手動同期 UI 稼働** + **データ安全性向上フェーズ完了** + **snapshot 障害対応・耐障害性強化完了**
**最新デプロイ**: PR #155 (832659d) Collector → `pay-collector-00035-gcd`（2026-05-31）/ PR #151 (c15e919) Dashboard → `pay-dashboard-00261-zfs`（2026-05-30）
**Cloud Run設定**: 2026-04-07 `--no-cpu-throttling --max-instances=3` 適用済み（ADR 0004 / 効果測定 2026-05-03 追記）+ pay-dashboard は PR #141 で `--timeout 900` 適用 + pay-collector に `--update-secrets=CHAT_WEBHOOK_URL=chat-webhook-url:latest`（PR #148）
**CI/CD**: ADR-0006、main push + パスフィルタで自動デプロイ、deploy 内に test gate 配置（PR #126）。`docs/operations/**` を paths trigger に追加（PR #139）
**テストスイート**: Dashboard **333** + Cloud Run **100** = **433テスト全PASS**（CI 上でも自動実行）

## ✅ 2026-05-31 セッション（完了）業務報告シート GAS Script ID 一元管理

業務報告スプレッドシート215件のコンテナバインド GAS の Script ID を収集し、スプレッドシート・メンバーと紐付けて BigQuery `gas_bindings` で一元管理。**完了・本番稼働**。PR #157 マージ済み（main、dashboard 本番反映）。

**背景**: スプレッドシート ID から Script ID を取得する公開 API は無い（Drive/Apps Script API/clasp 不可）。唯一の手段は各シートで「拡張機能→Apps Script」を開き遷移先 URL `.../projects/{SCRIPT_ID}/edit` から抽出する半手動巡回。スコープ: ID 紐付けメタデータのみ・読み取り専用。

### 巡回エンジン（重要な方針転換）
- python-playwright の persistent context は **Google が自動化セッションを信頼せず `auth_required`** で失敗（Cookie 保存済みでも再認証要求）。
- **解決 = ログイン済みで安定動作する Playwright MCP ブラウザの `run_code` ループで全件巡回**。1バッチ25件（MCP `run_code` の **300秒制限**。30件で約4分OK、40件は超過しタイムアウト）、各件 jitter、`#docs-extensions-menu` クリック→新タブ URL から Script ID 抽出。
- ロード: MCP 結果 JSON を `/tmp/load_batch.py`（`scripts/collect_gas_bindings.py` の `load_merge`/`check_create_times`/`utcnow_iso` を import）で createTime 検証 → staging→MERGE。BQ I/O は `bq` CLI（python ADC は別アカウントのため不使用）。

### 結果（Phase5検証 全PASS）
- 215件: **ok 213 / page_not_found 2 / suspicious(新規生成) 0**。distinct script_id 213・member紐付け漏れ0・ok_but_null 0。
- **取得不能2件**: こうちゃん（藤田 煌季 / a4cb3be1）・あーちゃん（藤田 梓稀 / cc375697）。member_master に URL あるが実シートが「ページが見つかりません」＝マスタURL古い/削除/権限変更。dashboard に `page_not_found` 表示、運用者が個別対応。
- dashboard「GAS管理」ページ本番稼働（admin閲覧専用・status別フィルタ・editor_urlリンク・clasp clone手順）。テスト dashboard 338 / cloud-run 100 PASS。

### 残作業（次セッション・コード整理のみ。本番データ投入は完了）
`scripts/collect_gas_bindings.py` の Codex 指摘整理（別PR）:
- **#4 死蔵コード削除**: python-playwright 巡回（`crawl_one`/`_do_login`/`main` + Playwright import/`AUTH_DIR`/`SHOT_DIR`）は MCP 経路移行で不使用 → 削除。残すのは `build_targets`/`load_existing`/`select_targets`/`check_create_times`/`load_merge`/`_bq_*` + MCP結果ロードCLI（`/tmp/load_batch.py` を `scripts/` に正式化）。
- **#1 fail-open 修正**: `check_create_times` が clasp/API 失敗時に警告のみ続行 → 検証不能をエラー扱いで停止。
- **#3**: `load_existing` が BQ エラーを「既存なし」扱い → 例外伝播。
- 取得不能2件（こうちゃん/あーちゃん）のマスタURL是正は運用者タスク（is decision-maker 領分）。

### 🔭 今後の方向性（2026-05-31 本田様共有・要記憶）— A1 セルに GAS Script ID 自動入力
- 「【共通】業務報告シート制御GASライブラリ」（Script ID: `1hDSPvY91iCGLoK_1FhqQK-DhT3DpVtDuXH9ZTOAxAjuIat-p4lEY2egj`）を各業務報告スプレッドシートに順次導入中。**導入済みシートは「【都度入力】業務報告」タブの A1 セルに自身の GAS Script ID が自動入力される想定**（業務報告スプレッドシート＝複数タブ構成。A1 が入るのは先頭タブではなく **`【都度入力】業務報告` タブ**）。ライブラリ参照への書き換えは GAS 配信ツール（Script ID `1DJeYyPnr6ImxP4WMZ03StQhjlOmfa37v7iiDQAwi3yGkFAt4J0xlMAtb`）で実施（**GAS からのアプローチは一旦完了**）。
- **含意（将来の収集方式の転換）**: `【都度入力】業務報告` タブ A1 が「各シートが自分の Script ID を申告する場所」になると、現状の半手動巡回（`collect_gas_bindings.py` / Playwright MCP）が不要になり、**各シートの `'【都度入力】業務報告'!A1` を Sheets API で一括 batchGet するだけ**で `gas_bindings` を再構築可能 → Cloud Run 毎朝バッチに組込できる方向。
- **配信時の制約（2026-05-31 検証）**: GAS 実行での一括書き換えは ① Apps Script API 管理系クォータ `scriptManagementApiQpsPerUser`=60/min/{project}/{user}（429 RESOURCE_EXHAUSTED）② GAS 6 分実行制限 の二重制約。clasp/ローカル移行でも 429 は同じ（同一 API 消費。consumer project を変えればバケットは分かれるが上限 60 は不変）だが、**6 分制限はローカル実行で解放**。推奨 = ローカル Apps Script API バッチ（スロットリング 2.5–3 秒/件 + 指数 backoff + チェックポイント再開）。call 数削減（`getContent` 省略で `updateContent` のみ→1 件 1 call）も有効。
- **関連作業（完了済み）**: 管理用スプレッドシート `130a5JLj2NXj-WTt44HYDMCMAHpuhmm9sq47yOYRlKBs` の「シート3」A 列に、現時点の `gas_bindings` status=ok 全 213 件の Script ID 一覧を記入済み（member_id 順・完全上書き・読み返し検証 OK、Sheets API + Drive スコープ）。

## 🆕 2026-05-31 セッション完了サマリー（snapshot 障害対応 + 耐障害性強化）

発端: 朝6時バッチで Step0 snapshot が `deleteSnapshot` 権限不足により**5件全失敗**（Chat 通知で検知）。原因特定 → 恒久対応 → 事後強化を段階実施（各分岐に Codex セカンドオピニオン + 本田様判断を挟み、過剰実装を回避）。

| PR | 内容 | マージ | 備考 |
|----|------|--------|------|
| #153 | BQ snapshot に必要な IAM 手順を追記（障害恒久対応） | 2419f4a | expiration付き `CREATE SNAPSHOT` は `deleteSnapshot` を要求するが `dataEditor` に無い。`pay_reports_backup` に dataOwner(OWNER ACL) 付与 + 今日分5件を手動補完 |
| #154 | snapshot 復旧手順 + Step0 健全性チェックを追記 | 7afd992 | 非破壊リストアを実証（`CREATE TABLE CLONE`、件数26→26・スキーマ一致）。健全性チェック: `INFORMATION_SCHEMA.TABLE_SNAPSHOTS` で当日5件確認 |
| #155 | snapshot 失敗日は Step5 をスキップ（fail-safe） | 832659d | バックアップ無しで唯一ソースを破壊的変更しない。毎朝バッチ `POST /` のみ、手動 `/update-groups` は対象外。tests +3。**本番デプロイ成功**（pay-collector-00035-gcd） |

### 原因（PR #153）
- `create_snapshots()` は `OPTIONS(expiration_timestamp=90日)` 付き `CREATE SNAPSHOT TABLE` を実行 → `bigquery.tables.deleteSnapshot` を要求（失効＝将来の削除と同義）
- pay-collector@ は `roles/bigquery.dataEditor` のみ（`createSnapshot` はあるが `deleteSnapshot` 無し）→ 403
- 本処理 Step1-7 は正常完了しデータは無傷。PR #146 デプロイ時の IAM 付与漏れが本質
- グローバル memory に `reference_bigquery_snapshot_expiration_permission.md` 追加

### Step5 fail-safe（PR #155）
- `dashboard_users` の snapshot が成功した日のみ Step5（破壊的 MERGE/DELETE）を実行。失敗日はスキップ + Chat 通知（翌日 snapshot 成功時に差分同期で追いつく）
- 判定: `isinstance(snapshot_results, dict) and snapshot_results.get(config.BQ_TABLE_DASHBOARD_USERS) == 1`。`main.py` に `import config` 追加

### 残務・将来候補（保留＝着手は本田様判断）
- **明朝(20260601)バッチで pay-collector@ 実権限の snapshot 成功を確認** — CLAUDE.md「Step0 健全性チェック」クエリで当日5件を確認（実行は本田様、成功時は無通知のため能動確認が必要）
- **Phase 2-C**（権限棚卸し1枚 + `dataOwner`→custom role 縮小評価）/ **Phase 3**（保持期間90日・復旧目標の記録、定期リストア確認ルール）は **ROI 逓減 + decision-maker 領分のため保留**。実運用で必要性が見えたとき or 運用判断時に着手

## 🆕 2026-05-30 セッション完了サマリー（データ安全性向上）

発端: ユーザーから「BigQuery のバックアップを取っていたか？」の問い。Codex セカンドオピニオン + リスク×効果バランス分析を経て、データ安全性を 2 段階で向上。

| PR | 内容 | マージ | 備考 |
|----|------|--------|------|
| #146 | BQ唯一ソース5テーブルの日次 snapshot バックアップ（Step0・90日自動失効・別データセット） | 7d4dc93 | Codex 指摘で snapshot を本処理前(Step0)へ移動、復旧 runbook 追加。Cloud Run tests +9 |
| #147 | バッチ障害の Google Chat 自動通知（no-op 段階デプロイ） | 0caa5aa | 5エンドポイント統合、Codex 指摘 Medium3+Low1 全対応（URL漏洩防止含む）。tests +14 |
| #148 | CHAT_WEBHOOK_URL 注入で通知を有効化 | d0df8e2 | Secret Manager 投入 + deploy.yml 更新、疎通確認済み |
| #149 | Chat通知に正式システム名称を表示 | 360a0f2 | 「タダカヨ 活動時間・報酬マネジメントダッシュボード（データ収集バッチ / pay-collector）」 |
| #151 | アーキテクチャ図・CLAUDE.md にドキュメント反映 | c15e919 | architecture.py に Step0/Chat通知を図示、CLAUDE.md にテスト件数97・新ファイル・新インフラ反映。運用ドキュメントページは自動glob で対応不要だった |

### BQ snapshot バックアップ（R2、PR #146）
- 対象: **BQが唯一のソース**（Sheets/Admin Directory から再生成不可）の5テーブル — `dashboard_users` / `dashboard_sync_groups` / `check_logs` / `wam_target_projects` / `withholding_targets`
- 毎朝バッチ **Step0**（本処理の前 = 直近正常状態を保全）で `pay_reports_backup` データセットへ `CREATE SNAPSHOT TABLE`、90日で自動失効
- 再生成可能テーブル（gyomu/hojo/members/member_master）は対象外。rename 等の非常時のみ手動 snapshot（R1、`20260516_活動分類_rename.md` §5.5）
- 実装: `cloud-run/bq_loader.py` `create_snapshots()` / `main.py` Step0。復旧手順: `docs/operations/20260530_BQ_snapshot復旧手順.md`
- 見送り: R3 部分失敗アラート（→ Chat 通知で実質カバー）、R4 cross-region DR（小規模に過剰）

### Chat 障害通知（PR #147-149）
- 5エンドポイント（`/` `/update-groups` `/sync/×3`）の致命的エラーを即通知 + 毎朝バッチ `POST /` の部分失敗（Step0-7）を末尾集約通知
- 通知方式: Google Chat Incoming Webhook（urllib、依存ゼロ増）。webhook URL は Secret Manager `chat-webhook-url` → env `CHAT_WEBHOOK_URL`、**未設定なら no-op**
- 通知内容: テクニカルのみ（システム名 / Step名 / 例外型 / メッセージ / JST時刻 / リビジョン）。投稿先スペースは運用管理者限定で PII マスクなし方針
- 通知は付随処理として完全隔離（`notify` 全体を except Exception で握り、URL を含む例外もログに出さない）
- 実装: `cloud-run/chat_notifier.py` / `main.py`。運用: `docs/operations/20260530_Chat障害通知.md`

### 構築済みインフラ（このセッション）
| リソース | 状態 |
|---|---|
| BQ データセット `pay_reports_backup` | 作成済み（asia-northeast1、`infra/bigquery/backup_dataset.sql`） |
| Secret `chat-webhook-url` | 作成済み（version 1 enabled、webhook 再生成 + read -s 登録） |
| `pay-collector@` SA secretAccessor | `chat-webhook-url` に付与済み |

### 設計判断・教訓（Codex セカンドオピニオン経由）
| 判断 | 理由 |
|---|---|
| snapshot は本処理**前**(Step0) | バッチ実行前の正常状態を保全、Step5 誤動作や UI 誤操作から守る。初回デプロイ無防備期間も解消 |
| 通知ログから webhook URL を除外 | safe-refactor で except を広げた副作用で URL を含む ValueError がログに出る経路が顕在化 → 例外型名のみログ |
| webhook URL の安全な扱い | チャット平文露出 → 再生成 + `read -s` 経由で Secret 登録（shell history / ツールログに残さない） |
| 通知名称は正式名 + 発生元併記 | 発生元は collector バッチ。ダッシュボード（pay-dashboard）とは別サービスのため「データ収集バッチ (pay-collector)」を明示 |

### Issue 変化（Net 0）
- Close: 0 件 / 起票: 0 件 / **Net: 0 件**
- 全作業がユーザー明示指示の新機能実装で、即実装→即マージで完了（triage 基準上、Issue 化対象なし）。Net 0 だが PR 4本マージで進捗あり

### 残課題・次セッション候補
- **実投稿確認**: ユーザー判断で疎通テスト投稿は実施済み（HTTP 200）。新文面（PR #149）での確認は「不要」と判断 → 次回実障害時に自然確認
- 既存 Open Issue #94 / #58 / #54 は外部ブロッカー待ちで据え置き

## 🆕 2026-05-17 セッション完了サマリー

| PR | 内容 | マージ | 備考 |
|----|------|--------|------|
| #141 | admin 画面に手動同期ボタン (4 種) + Cloud Run /sync/* 3 endpoint + OIDC ヘルパ + dashboard `--timeout 900` | 9c4b72c | Cloud Run tests +7 件 (63→70)、Codex review High 指摘反映 |
| #142 | CLAUDE.md の IAM 設定を「既存環境で付与済」に明示 | 02cd7e9 | 訂正 PR、新規環境構築時のみ実行する手順として整理 |
| #143 | 活動分類 rename 手順書から重複セクション 4.3 を削除 | 1fff689 | 4.2 表に Playwright 行 1 行追加 + 4.3 (11 行) 削除、情報集約 |

### Connected Sheets 連携の入口整備
- ユーザーが `v_monthly_compensation` を Google Sheets の「データコネクタ → BigQuery」で接続成功 → BQ VIEW を Sheets に出す導線が完成
- これに合わせて「BQ 側を今すぐ最新化したい」ニーズに応える手動同期ボタンを admin 画面に追加（PR #141）

### 追加された手動同期エンドポイント（pay-collector）

| ボタン | エンドポイント | 想定所要時間 | 対象テーブル |
|---|---|---|---|
| メイン報告 | `POST /sync/main-reports` | 約 5.5 分 | gyomu_reports / hojo_reports / members / groups_master（Step 1-3 + Step 4 グループ情報復元込み） |
| 立替金 | `POST /sync/reimbursement` | 約 1 分 | reimbursement_items |
| タダメンM | `POST /sync/member-master` | 数十秒 | member_master |
| グループ情報のみ | `POST /update-groups`（既存） | 約 2 分 | members / groups_master / dashboard_users |

実装は WRITE_TRUNCATE（既存パターン踏襲）、同時実行ロックなし、実行履歴永続化なし。dashboard / pay-collector は共通 SA `pay-collector@` で動作する self-invoke 構成。

### Codex review 経由で発見・修正した設計欠陥（PR #141 内）
**High**: `/sync/main-reports` が `run_collection()` だけ呼ぶと `members.groups` が空文字で WRITE_TRUNCATE される（通常バッチ POST / は直後の Step 4 で復元している前提が単独 endpoint では崩れる）→ ダッシュボードのグループ別表示が壊れる。修正: `sync_main_reports` 内で続けて `update_member_groups_from_bq()` を呼ぶよう変更、所要時間 4 分 → 5.5 分に再設定。

**Medium 反映**: 同期成功直後に `st.cache_data.clear()` を呼ぶ（BQ 更新済みでも dashboard が最大 1 時間古いまま見える問題を解消）。
**Medium 見送り**: `bq_loader.load_all()` の `-1` failure をエラー扱いにする partial_error 検知ロジックは「無理のない範囲」で見送り。
**Low 反映**: 関数外途中 import (`# noqa: E402`) を先頭の import 群に移動。

### IAM 既付与の確認（PR #142 の経緯）
PR #141 description / CLAUDE.md で「`pay-collector@` SA に `roles/run.invoker` 付与必須」と記載したが、`gcloud run services get-iam-policy` で確認したところ **既に付与済**（既存 `check_management.py` の self-invoke 用途で過去に付与）。CLAUDE.md を「新規環境構築時のみ実行」記述に訂正 + 確認コマンド追加（PR #142）。

教訓を global memory に記録: `feedback_iam_state_check_before_declare.md`
- IAM 等の運用変更を「必須」と書く前に既存状態を確認する
- ユーザー明示指示の revocable 運用変更 (IAM 追加等) は AI executor で実行する（decision-maker 領分を過剰に拡大解釈しない）

### 設計判断ログ（Codex セカンドオピニオン 2 回経由で合意）
| 判断 | 採用理由 |
|---|---|
| 同時実行ロックなし | 朝 6 時バッチと手動操作の時間帯衝突は実運用上稀、WRITE_TRUNCATE で「最新が勝つ」前提を許容 |
| 実行履歴永続化なし | BQ `ingested_at` + テーブルメタデータ `modified` で代替（既存「BQ テーブル情報」セクションで表示済） |
| dashboard 側テスト省略 | 運用 2 名で手動 UI 検証即気付ける、過剰実装回避 |
| pay-dashboard 専用 SA 分離 | Phase 1 では self-invoke 採用、`cloud_run_client.py` に TODO 残し |
| メンバー単位の部分更新 | WRITE_TRUNCATE 設計のため別 PR で要件確定後に着手（Phase 3 候補） |
| Cloud Tasks / 202 accepted 非同期化 | Phase 2 候補（実行履歴永続化が必要になった時点で検討） |

### Issue 変化（Net 0）
- Close: 0 件
- 起票: 0 件
- Net: **0 件**

**理由言語化**: 今セッションはユーザー要望「無理のない範囲で機能追加」「過剰実装回避」を主軸とし、CLAUDE.md triage 基準（実害/再現バグ/CI破壊/rating≥7/明示指示）に該当する事象なし。Codex review の Medium 指摘 (`-1` failure 検知) も「無理のない範囲」で PR コメント記録に留めた。既存 Open Issue (#94 / #58 / #54) は前提条件未満（GCP 課金権限取得 / 外部ツール所在確認 / Phase 0 回答受領）のため着手不可。質的な進展は ① 機能追加 PR 1 件 ② doc 整備 PR 2 件 ③ memory 学習記録 1 件 ④ 既存テスト 7 件追加、累計 403 件全 PASS。

### 動作確認まち（ユーザー側）
1. admin で `pay-dashboard` の「管理設定」→「手動同期」セクション表示確認（4 ボタン + eta caption）
2. 「タダメンMマスタ」ボタン押下（影響最小、数十秒）→ spinner → 「完了（X 秒、データキャッシュもクリア済）」+ JSON 表示
3. 「BigQuery テーブル情報」セクションをリロード → `member_master` の「最終更新」が直近 JST に更新
4. 余裕があれば「メイン報告」ボタン（約 5.5 分）を朝バッチと衝突しない時刻に 1 回試行
5. PR #143 反映確認（運用ドキュメントページの活動分類 rename 計画書、4.2 表に Playwright 行があり 4.3 セクションが消えている）

### 軽微な保守メモ（前セッションから持ち越し、別 PR スコープ）
- Node.js 20 deprecation 警告（actions/checkout@v4 等、2026-06-02 以降強制 v24）→ workflow メンテで一括対応
- `html.escape(code)` 対応（mermaid_renderer + architecture.py 全体整合）
- selectbox の同名重複対策（`format_func` で DocEntry 直接渡し）
- dashboard UI の DML 例外ハンドリング統一（PR #132 review I1+I2、rating 7 相当だが頻度低のため起票見送り TODO）
- `bq_loader.load_all()` の `-1` failure → partial_error 検知（Codex PR #141 review Medium、運用負荷増えたら検討）
- pay-dashboard 専用 SA 分離（PR #141 cloud_run_client.py TODO、SA 境界の明確化が必要になったら検討）

## 🆕 2026-05-16 セッション完了サマリー

| PR | 内容 | マージ | 備考 |
|----|------|--------|------|
| #139 | 運用ドキュメントページを dashboard に追加 + Mermaid renderer 共通化 + 業務報告シート「活動分類」rename 計画書 1本目配置 | 89ec1ca | 新規ページ + `docs/operations/` 基盤 + workflow に docs 同梱ステップ、16 テスト追加 |

### 検証完了事項（業務報告シート「活動分類」カラム名変更）
ユーザーからの相談を発端に、`活動分類` ヘッダー名の変更が現システムに与える影響を多層検証:

| 観点 | 結論 | 論拠 |
|------|------|------|
| Cloud Run collector | **影響なし** | 範囲ベース取得 `B7:K`、ヘッダー行は読み取り範囲外（`data_start_row=7`） |
| BigQuery スキーマ・VIEW | **影響なし** | 英語識別子 `activity_category` で固定、日本語はコメントのみ |
| Streamlit dashboard | **影響なし** | BQ 英語列名で参照、UI 表示「活動分類」は内部文字列で独立 |
| 旧 GAS (`コード.js`) | **影響なし** | 稼働停止中 + 位置ベース参照 |
| シート内ワークシート関数 / バインド GAS | **影響なし** | ユーザー確認済 |

Codex セカンドオピニオン取得済（4 MINOR / 1 NIT、BLOCKER なし）。実施時は **一時利用スタンドアロン GAS + clasp** が最適解。Playwright MCP は不要（脆い・過剰）。詳細は dashboard「運用ドキュメント」→ `2026-05-16 業務報告シート「活動分類」カラム名変更 計画書` で全員閲覧可。

### 新規追加された基盤
| 項目 | 内容 |
|------|------|
| `dashboard/_pages/operations_docs.py` | 運用ドキュメント表示ページ（frontmatter + Mermaid 自動分割） |
| `dashboard/lib/mermaid_renderer.py` | Mermaid レンダリング共通モジュール（`architecture.py` から切り出し） |
| `docs/operations/` | 運用ドキュメント実体（README + 1本目: 活動分類 rename 計画書） |
| `.github/workflows/deploy-dashboard.yml` | docs/operations を build context に同梱するステップ追加 + paths trigger 拡張 |

### Issue 変化（Net 0）
- Close: 0 件
- 起票: 0 件
- Net: **0 件**（機能追加のみ、既存 Issue とは独立）

### 動作確認まち（ユーザー側）
1. dashboard で「運用ドキュメント」メニュー表示
2. selectbox に「2026-05-16 業務報告シート「活動分類」カラム名変更 計画書」が出る
3. Markdown + Mermaid 図 3個 + 表が描画される
4. user / checker / admin 各ロールでアクセス可能

## 🆕 2026-05-13 セッション完了サマリー

| PR | 内容 | マージ | 備考 |
|----|------|--------|------|
| #135 | 報告入力を (仮) UI ドラフト化、admin 限定に変更 | 0e5bbd3 | `require_user` → `require_admin`、警告バナー追加、ナビ位置 admin_pages へ |
| #136 | 報告入力の保存処理を dry-run 化（BQ 書き込み無効） | 3dc13a4 | `logger.info` のみ、UI トースト変更、テスト書き換え |
| #137 | (仮)報告入力に仕様/アーキテクチャ折り畳みメモ追加 | a080907 | `st.expander` + `st.graphviz_chart` × 2、自己完結ドキュメント |

### 方針転換
- 報告入力ページを「実装着手済みプロトタイプ」→「**UI 提案ドラフト（admin プレビュー）**」に位置づけ直し
- 本番 BQ への書き込み影響を**完全皆無化**（dry-run）
- 採用判断後の手順・不採用時の削除対象をページ内 expander に明記（外部 docs 依存なし）

### Issue 変化（Net -1）
- ✅ Close: **#93**（app_gyomu_reports / app_hojo_reports テーブル作成）— テーブル実体は既に存在しており「達成済み」として close
- 起票: 0 件
- Net: **-1 件**（KPI 進捗 +1）

### 「(仮) 報告入力」ページの最終状態（採用判断待ち）
| 観点 | 状態 |
|------|------|
| 表示対象 | admin ロールのみ |
| 保存処理 | dry-run（BQ 未呼出、`logger.info` のみ） |
| 仕様ドキュメント | ページ内 expander に折り畳み（admin 自己完結） |
| 採用時の再開手順 | ページ内 expander §5 に 6 ステップ明記 |
| 不採用時の削除対象 | ページ内 expander §6 に明記 |

---

> **2026-05-02 〜 2026-05-03 セッションの履歴は [archive/2026-05-history.md](archive/2026-05-history.md) へ移動済**（2026-05-17 アーカイブ実施）
> 含む内容: PR #119 / #121-#124 / #126 / #127 / #128 / #131 / #132 / #133、GitHub Actions CI/CD 導入、グループ自動同期 ON/OFF、ADR-0004 効果測定、業務報告 日付ソート修正、=HYPERLINK() URL 取得対応、deploy test gate

---

## WAM助成金対応 全体状況

### 要件達成状況

| # | 要件 | 区分 | 状態 | PR |
|---|------|------|------|-----|
| #55 | 領収書PDF自動生成 | Must | ✅ 完了 | #86 |
| #56 | 振込CSV出力（GMOあおぞら形式） | Must | ✅ 完了 | #83 |
| #57 | WAM月別報酬・源泉確認ツール | Must | ✅ 完了 | #81 |
| #92 | 振込CSV口座自動化 | 基盤 | ✅ 完了 | #96 |
| #58 | 支払調書連携 | Want | 🔶 部分完了 | #97（年間CSV出力済、外部ツール連携は所在確認待ち） |

**Must 3/3 完了、Want 部分完了、技術側でやれることは全完了**

### ドラフト→正式化に必要な残作業

| 項目 | 工数 | ブロッカー |
|------|------|-----------|
| wam_flag を 'Y' に更新 | 5分 | Phase 0 回答（どのPJがWAM対象か確定） |
| #58 外部ツール連携 | 不明 | 外部ツール所在確認 |
| 実データ受入テスト | 30分 | ユーザー確認 |
| 「ドラフト」ラベル除去 | 5分 | 上記完了後 |

### ダッシュボード Tab 構成（WAM立替金・報酬確認ページ）

| Tab | 内容 | PR |
|-----|------|-----|
| 1 | PJ別サマリー | #75 |
| 2 | メンバー別明細 | #75 |
| 3 | 領収書添付状況 | #75 |
| 4 | 月別報酬・振込確認（口座自動入力済） | #81, #83, #96 |
| 5 | 支払明細書PDF | #86 |
| 6 | 年間支払調書データ（個人情報はCSVのみ） | #97, #99 |

---

## オープンIssue（2026-05-17 時点）

| # | タイトル | 優先度 | ブロッカー |
|---|---------|--------|-----------|
| #58 | 支払調書 外部ツール連携 | Want/P2 | 外部ツール所在未確認 |
| #94 | Cloud Run コスト監視 | P2 | 課金アカウント `013C90-D4C0A0-A391D6` への billing.admin 権限取得待ち（部分達成 PR #131 マージ済） |
| #54 | Phase 0 ステークホルダー確認 | documentation, P2 | 回答待ち |

(#93 は 2026-05-13 セッションで close 済)

## デプロイ現況（2026-05-17 時点）

| サービス | 最新 Rev | 内容 |
|---------|----------|------|
| Collector | PR #141 デプロイ後の最新 | `/sync/main-reports` `/sync/reimbursement` `/sync/member-master` 3 endpoint 追加 |
| Dashboard | PR #143 Deploy 完了後 | admin 画面に手動同期ボタン 4 種 + 運用ドキュメント (PR #143 反映) + `--timeout 900` 適用 |

最新リビジョン名は `gcloud run services describe pay-{collector,dashboard} --region=asia-northeast1 --project=monthly-pay-tax --format='value(status.latestReadyRevisionName)'` で取得可。

## センシティブデータ方針

member_master由来のデータ（口座・住所・氏名・フリガナ）は**ダッシュボードUIに一切表示しない**。
バックエンド処理（振込CSV、支払調書CSV等のファイル出力）でのみ利用。

## 🔴 次セッションの開始点

1. **手動同期ボタン動作確認**（2026-05-17 PR #141 デプロイ後の検証）
   - admin → 管理設定 → 手動同期セクションで 4 ボタン表示確認
   - 「タダメンMマスタ」ボタンで影響最小の試行（数十秒）
   - 「BigQuery テーブル情報」セクションで `member_master` の「最終更新」が JST 直近に更新確認
2. **PR #143 反映確認** — 運用ドキュメントページの活動分類 rename 計画書、4.2 表に Playwright 行があり 4.3 セクションが消えている
3. **「(仮) 報告入力」採用判断** — admin が試用後、本採用 / 改変 / 廃止を判断（前セッションから持ち越し）
   - 本採用 → ページ内 expander §5「dry-run 解除の手順」(6 ステップ) で復活
   - 廃止 → ページ内 expander §6「不採用時の削除対象」に従って削除
4. **活動分類 rename 実行判断** — 影響分析完了済（2026-05-16）、新カラム名決定後に手順書 §5「実行フロー（3段階モデル）」に沿って実施
5. **#94 残作業** — 課金アカウントへの billing.admin 権限取得 + 予算アラート設定（ユーザー側 GCP コンソール操作）
6. **#58 外部ツール所在確認後** — 連携フォーマット決定 → CSV調整
7. **#54 Phase 0 回答受領後** — wam_flag UPDATE → ドラフトラベル除去

---

> テスト件数は `python3 -m pytest dashboard/tests/ -q && python3 -m pytest cloud-run/tests/ -q` で確認（**403件**、2026-05-17時点 / dashboard 333 + cloud-run 70）
> 過去の変更履歴・ファイル構成・アーキテクチャ図・BQスキーマ・環境情報は CLAUDE.md および `docs/handoff/archive/` を参照
