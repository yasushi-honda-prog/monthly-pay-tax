"""Vertex AI Gemini 評価エンジン (vertex_evaluator) のユニットテスト

spec: docs/specs/2026-06-10-team-budget-eval-design.md §5 / §7

Gemini SDK 呼び出しは全てモック。
"""

from unittest.mock import MagicMock, patch

import pytest

import vertex_evaluator
from vertex_evaluator import (
    EvaluationValidationError,
    GeminiCallError,
    build_samples_text,
    build_user_prompt,
    compute_actual_data_hash,
    generate_comment,
    judgment_context_for,
    load_team_samples,
)


VALID_COMMENT = (
    "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
    "業務の偏りも見られず、活動分類のバランスも保たれた良好な状態となっています。\n"
    "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
)


class TestJudgmentContextFor:
    @pytest.mark.parametrize("rate, kw", [
        (100, "適正範囲内"),
        (80, "適正範囲内"),
        (120, "適正範囲内"),
        (79.9, "注意が必要"),
        (60, "注意が必要"),
        (120.1, "注意が必要"),
        (150, "注意が必要"),
        (59.9, "乖離が大きい"),
        (150.1, "乖離が大きい"),
        (200, "乖離が大きい"),
    ])
    def test_rate_to_context(self, rate, kw):
        assert kw in judgment_context_for(rate)

    def test_none_rate(self):
        assert "予算が未設定" in judgment_context_for(None)


class TestBuildUserPrompt:
    def _kwargs(self, **overrides):
        base = dict(
            year=2026, month=5, team="すごい隊",
            budget=500000, actual=480000,
            achievement_rate=96.0, diff=-20000,
            top_categories=[
                {"work_category": "訪問", "cnt": 12, "total_amount": 300000},
                {"work_category": "事務", "cnt": 5, "total_amount": 100000},
            ],
            samples_text="- 訪問 A\n- 訪問 B",
        )
        base.update(overrides)
        return base

    def test_contains_header_values(self):
        text = build_user_prompt(**self._kwargs())
        assert "2026年5月" in text
        assert "すごい隊" in text
        assert "¥500,000" in text
        assert "¥480,000" in text
        assert "96.0%" in text
        assert "-20,000" in text

    def test_top_categories_padded_to_3(self):
        """top_categories が 2 件しかなくても 3 行出力される"""
        text = build_user_prompt(**self._kwargs())
        assert "(該当なし)" in text

    def test_handles_none_budget(self):
        text = build_user_prompt(**self._kwargs(
            budget=None, achievement_rate=None, diff=None,
        ))
        assert "¥0" in text
        assert "—" in text  # rate / diff
        assert "予算が未設定" in text  # judgment_context

    def test_empty_samples_marked(self):
        text = build_user_prompt(**self._kwargs(samples_text=""))
        assert "(サンプルなし)" in text


class TestBuildSamplesText:
    """R5 新仕様: 戻り値が tuple[str, list[MaskResult]]"""

    def test_masks_member_names_in_samples(self):
        text, mask_results = build_samples_text(
            ["山田さんと訪問", "次回 03-1234-5678 に電話"],
            {"山田"},
        )
        assert "<MEMBER>" in text
        assert "<PHONE>" in text
        assert "山田" not in text
        assert "03-1234-5678" not in text
        # 2 description ぶんの MaskResult が返る
        assert len(mask_results) == 2
        # detected_* に raw 値が記録される (taint tracking)
        assert "山田" in mask_results[0].detected_names
        assert "03-1234-5678" in mask_results[1].detected_phone

    def test_empty_list_returns_empty(self):
        text, mask_results = build_samples_text([], set())
        assert text == ""
        assert mask_results == []

    def test_filters_empty_descriptions(self):
        text, mask_results = build_samples_text(
            ["有効", "", None, "有効2"], set()  # type: ignore[list-item]
        )
        assert text.count("\n") == 1  # 2 行 = 改行 1 つ
        assert "有効" in text
        assert len(mask_results) == 2  # 空・None は弾かれる

    def test_ac2_raw_pii_not_in_samples_text(self):
        """AC2: raw description に member name / email / phone があっても、
        samples_text (prompt 投入文字列) に raw 値は残らない。"""
        text, mask_results = build_samples_text(
            ["山田太郎さんから taro@x.com で連絡、090-1234-5678 にも"],
            {"山田太郎"},
        )
        assert "山田太郎" not in text
        assert "taro@x.com" not in text
        assert "090-1234-5678" not in text
        # MaskResult に raw 値が taint として記録され、後段の assert_no_raw_pii で
        # prompt 全体の二重検証に使われる
        assert "山田太郎" in mask_results[0].detected_names
        assert "taro@x.com" in mask_results[0].detected_email
        assert "090-1234-5678" in mask_results[0].detected_phone


class TestGenerateComment:
    def _mock_response(self, text: str, prompt_tokens=200, output_tokens=80):
        resp = MagicMock()
        resp.text = text
        usage = MagicMock()
        usage.prompt_token_count = prompt_tokens
        usage.candidates_token_count = output_tokens
        resp.usage_metadata = usage
        return resp

    def _mock_client(self, responses: list):
        client = MagicMock()
        client.models.generate_content.side_effect = responses
        return client

    def test_returns_first_valid(self):
        client = self._mock_client([self._mock_response(VALID_COMMENT)])
        text, usage = generate_comment(client, "prompt", sleep_fn=lambda _: None)
        assert text == VALID_COMMENT
        assert usage["attempts"] == 1
        assert usage["prompt_tokens"] == 200
        assert usage["output_tokens"] == 80
        assert usage["last_reason"] == ""
        assert client.models.generate_content.call_count == 1

    def test_retries_on_invalid_then_succeeds(self):
        client = self._mock_client([
            self._mock_response("短い"),  # 文字数不正
            self._mock_response(VALID_COMMENT),
        ])
        text, usage = generate_comment(client, "prompt", sleep_fn=lambda _: None)
        assert text == VALID_COMMENT
        assert usage["attempts"] == 2
        assert client.models.generate_content.call_count == 2

    def test_raises_on_max_attempts_exceeded(self):
        """初回 + 再生成 2 回 = 計 3 回まで試行、全部 NG なら EvaluationValidationError"""
        client = self._mock_client([
            self._mock_response("短い"),
            self._mock_response("もっと短い"),
            self._mock_response("また短い"),
        ])
        with pytest.raises(EvaluationValidationError) as excinfo:
            generate_comment(client, "prompt", sleep_fn=lambda _: None)
        assert "文字数不正" in str(excinfo.value) or "行数不正" in str(excinfo.value)
        assert client.models.generate_content.call_count == 3

    def test_raises_gemini_call_error_after_all_retries(self):
        """全試行で例外続き → GeminiCallError raise"""
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("network down")
        with pytest.raises(GeminiCallError):
            generate_comment(client, "prompt", sleep_fn=lambda _: None)
        # 初回 + 再生成 2 回 = 計 3 回試行
        assert client.models.generate_content.call_count == 3

    def test_retries_on_transient_then_succeeds(self):
        """Gemini call で transient failure → retry で成功"""
        client = MagicMock()
        client.models.generate_content.side_effect = [
            RuntimeError("503 transient"),
            self._mock_response(VALID_COMMENT),
        ]
        text, usage = generate_comment(client, "prompt", sleep_fn=lambda _: None)
        assert text == VALID_COMMENT
        assert usage["attempts"] == 2
        assert client.models.generate_content.call_count == 2

    def test_exponential_backoff_between_call_failures(self):
        """call failure 時の sleep は exponential (0.5s, 1.0s, ...)"""
        slept = []
        client = MagicMock()
        client.models.generate_content.side_effect = [
            RuntimeError("503"),
            RuntimeError("503"),
            self._mock_response(VALID_COMMENT),
        ]
        generate_comment(client, "prompt", sleep_fn=lambda s: slept.append(s))
        # 1 回目 fail → 0.5s, 2 回目 fail → 1.0s, 3 回目 success → no sleep
        assert slept == [0.5, 1.0]

    def test_validates_against_email_pii(self):
        """R5: email リークコメントは検証 NG → 再生成。member_names 引数はもう取らない。"""
        leak = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "詳細は info@example.com まで連絡が必要、と案内された案件もありました。\n"
            "来月以降も予算進捗の中間モニタリングを継続し、早期の乖離検知を推奨します。"
        )
        client = self._mock_client([
            self._mock_response(leak),
            self._mock_response(VALID_COMMENT),
        ])
        text, usage = generate_comment(client, "prompt", sleep_fn=lambda _: None)
        assert text == VALID_COMMENT
        assert usage["attempts"] == 2

    def test_validates_against_member_master_name_no_longer_rejects(self):
        """R5 重要: 旧仕様で「山田太郎」がコメントに出ると reject されていたが、
        新仕様では validate が member_names を参照しないため reject されない。
        この test は連鎖障害 (PR #233-#241) の構造的 false reject 解消を担保する。"""
        # 「山田太郎」を含むコメントを Gemini が返した想定 (普通名詞ではないが、
        # 例えば description 由来でない hallucination の可能性)
        text_with_name = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "今月は山田太郎さんの活動が顕著で、補助活動も伸びている状況が見られます。\n"
            "来月以降も予算進捗の中間モニタリングを継続し、早期の乖離検知を推奨します。"
        )
        client = self._mock_client([self._mock_response(text_with_name)])
        # R5: validate は通る (PII 対策は入口 mask_pii に一本化されているため)
        text, usage = generate_comment(client, "prompt", sleep_fn=lambda _: None)
        assert text == text_with_name
        assert usage["attempts"] == 1

    def test_sleeps_between_attempts(self):
        slept = []
        client = self._mock_client([
            self._mock_response("短い"),
            self._mock_response(VALID_COMMENT),
        ])
        generate_comment(client, "prompt", sleep_fn=lambda s: slept.append(s))
        # 1 回目失敗後に sleep が入る
        assert slept == [0.5]


class TestComputeActualDataHash:
    def _client_returning(self, data_hash_value):
        client = MagicMock()
        row = {"data_hash": data_hash_value}
        client.query.return_value.result.return_value = [row]
        return client

    def test_returns_hash(self):
        client = self._client_returning("abcdef123456")
        result = compute_actual_data_hash(client, 2026, 5, "X 隊")
        assert result == "abcdef123456"

    def test_returns_empty_when_null(self):
        client = self._client_returning(None)
        assert compute_actual_data_hash(client, 2026, 5, "X 隊") == ""

    def test_returns_empty_when_no_rows(self):
        client = MagicMock()
        client.query.return_value.result.return_value = []
        assert compute_actual_data_hash(client, 2026, 5, "X 隊") == ""

    def test_query_uses_year_month_team_params(self):
        client = self._client_returning("h")
        compute_actual_data_hash(client, 2026, 5, "Z 隊")
        # job_config が ScalarQueryParameter を含むことを軽く確認
        _, kwargs = client.query.call_args
        params = kwargs["job_config"].query_parameters
        names = [p.name for p in params]
        assert "year" in names and "month" in names and "team" in names

    def test_sql_avoids_reserved_keyword_rows(self):
        """CTE 名に `rows` を使うと BigQuery 予約語 ROWS と衝突する。回帰防止。"""
        client = self._client_returning("h")
        compute_actual_data_hash(client, 2026, 5, "Z 隊")
        sql = client.query.call_args.args[0]
        assert "WITH rows AS" not in sql
        assert "FROM rows" not in sql


class TestLoadTeamSamples:
    def _client_returning(self, top, samples):
        client = MagicMock()
        row = {"top_categories": top, "sample_descriptions": samples}
        client.query.return_value.result.return_value = [row]
        return client

    def test_returns_empty_when_no_rows(self):
        client = MagicMock()
        client.query.return_value.result.return_value = []
        top, samples = load_team_samples(client, 2026, 5, "X")
        assert top == []
        assert samples == []

    def test_returns_empty_when_null_arrays(self):
        client = self._client_returning(None, None)
        top, samples = load_team_samples(client, 2026, 5, "X")
        assert top == []
        assert samples == []

    def test_parses_dict_rows(self):
        client = self._client_returning(
            [{"work_category": "訪問", "cnt": 5, "total_amount": 100000}],
            ["訪問内容 A", "訪問内容 B"],
        )
        top, samples = load_team_samples(client, 2026, 5, "X")
        assert top == [{"work_category": "訪問", "cnt": 5, "total_amount": 100000}]
        assert samples == ["訪問内容 A", "訪問内容 B"]

    def test_preserves_zero_values(self):
        """cnt=0 / total_amount=0 が None に化けないこと
        (`a or b` パターンで 0 が falsy 扱いされる bug 防止)"""
        client = self._client_returning(
            [{"work_category": "事務", "cnt": 0, "total_amount": 0}],
            [],
        )
        top, _ = load_team_samples(client, 2026, 5, "X")
        assert top[0]["cnt"] == 0
        assert top[0]["total_amount"] == 0


class TestHashSqlOrderTieBreaker:
    def test_sql_includes_row_json_tie_breaker(self):
        """同一 row_hash 重複時の順序不定を防ぐため、ORDER BY に row_json を含む"""
        import vertex_evaluator as ve
        assert "ORDER BY row_hash, row_json" in ve._HASH_SQL


class TestBuildGenaiClientTimeout:
    def test_timeout_is_passed_to_http_options(self):
        """EVAL_TIMEOUT_SEC が HttpOptions.timeout (ms) に渡される"""
        import vertex_evaluator as ve
        with patch("vertex_evaluator.genai.Client") as mock_client_cls:
            ve.build_genai_client()
            _, kwargs = mock_client_cls.call_args
            http_opts = kwargs["http_options"]
            # types.HttpOptions の timeout 属性 (SDK バージョン依存)
            assert getattr(http_opts, "timeout", None) == 60 * 1000  # EVAL_TIMEOUT_SEC default


class TestBuildGenaiClient:
    def test_uses_vertex_ai_with_region(self):
        """asia-northeast1 でクライアントが構築される（データレジデンシー）"""
        with patch("vertex_evaluator.genai.Client") as mock_client_cls:
            vertex_evaluator.build_genai_client()
            _, kwargs = mock_client_cls.call_args
            assert kwargs["vertexai"] is True
            assert kwargs["location"] == "asia-northeast1"
            assert kwargs["project"] == "monthly-pay-tax"


class TestBuildGenerationConfig:
    def test_includes_system_prompt_and_safety(self):
        cfg = vertex_evaluator.build_generation_config()
        # types.GenerateContentConfig のフィールドアクセスは SDK バージョン依存だが、
        # system_instruction と safety_settings は最低限保持されるはず
        assert cfg.system_instruction == vertex_evaluator.SYSTEM_PROMPT
        assert cfg.max_output_tokens == 350
        assert cfg.temperature == 0.3
        assert cfg.top_p == 0.8
        # safety_settings は 4 カテゴリ
        assert len(cfg.safety_settings) == 4

    def test_thinking_budget_zero(self):
        """Gemini 2.5 系の thinking バグ対策: thinking_budget=0 で無効化されること。

        thinking がデフォルト有効だと max_output_tokens の枠を thinking が消費し、
        最終応答テキストが空 → validate_ai_comment("empty") → EvaluationValidationError
        で 3 回リトライ後に失敗する本番障害が発生した。本テストは設定が抜けないよう監視する。
        """
        cfg = vertex_evaluator.build_generation_config()
        assert cfg.thinking_config is not None
        assert cfg.thinking_config.thinking_budget == 0


class TestDescribeResponseForDebug:
    """PR #236 後も `validation NG: empty` 継続障害の切り分け用デバッグログヘルパー。"""

    def _mock_safety(self, category: str, probability: str, blocked: bool = False):
        m = MagicMock()
        m.category = category
        m.probability = probability
        m.blocked = blocked
        return m

    def _mock_response(
        self, finish_reason=None, safety=None, thoughts=None, candidates=None, tokens=True,
    ):
        resp = MagicMock()
        if candidates is None:
            c0 = MagicMock()
            c0.finish_reason = finish_reason
            c0.safety_ratings = safety or []
            resp.candidates = [c0]
        else:
            resp.candidates = candidates
        if tokens:
            usage = MagicMock()
            usage.prompt_token_count = 1000
            usage.candidates_token_count = 0
            usage.thoughts_token_count = thoughts
            usage.total_token_count = 1000 + (thoughts or 0)
            resp.usage_metadata = usage
        else:
            resp.usage_metadata = None
        return resp

    def test_collects_finish_reason_and_safety(self):
        resp = self._mock_response(
            finish_reason="FinishReason.MAX_TOKENS",
            safety=[
                self._mock_safety("HarmCategory.HARM_CATEGORY_HATE_SPEECH",
                                  "HarmProbability.NEGLIGIBLE"),
            ],
        )
        info = vertex_evaluator._describe_response_for_debug(resp)
        assert info["candidate"]["count"] == 1
        assert info["candidate"]["finish_reason"] == "MAX_TOKENS"
        assert info["candidate"]["safety"][0]["category"] == "HARM_CATEGORY_HATE_SPEECH"
        assert info["candidate"]["safety"][0]["probability"] == "NEGLIGIBLE"
        assert info["candidate"]["safety"][0]["blocked"] is False
        assert info["tokens"]["prompt"] == 1000

    def test_thoughts_token_count_surfaced(self):
        """thoughts_token_count が 0 でないなら thinking_budget=0 無視を疑う"""
        resp = self._mock_response(finish_reason="STOP", thoughts=300)
        info = vertex_evaluator._describe_response_for_debug(resp)
        assert info["tokens"]["thoughts"] == 300

    def test_empty_candidates_no_crash(self):
        resp = self._mock_response(candidates=[])
        info = vertex_evaluator._describe_response_for_debug(resp)
        assert info["candidate"] == {"count": 0}
        assert info["tokens"]["prompt"] == 1000

    def test_no_usage_metadata_no_crash(self):
        resp = self._mock_response(finish_reason="STOP", tokens=False)
        info = vertex_evaluator._describe_response_for_debug(resp)
        assert info["tokens"]["prompt"] is None
        assert info["tokens"]["thoughts"] is None
