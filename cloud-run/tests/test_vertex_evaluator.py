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
    def test_masks_member_names_in_samples(self):
        masked = build_samples_text(
            ["山田さんと訪問", "次回 03-1234-5678 に電話"],
            {"山田"},
        )
        assert "<MEMBER>" in masked
        assert "<PHONE>" in masked
        assert "山田" not in masked
        assert "03-1234-5678" not in masked

    def test_empty_list_returns_empty(self):
        assert build_samples_text([], set()) == ""

    def test_filters_empty_descriptions(self):
        text = build_samples_text(["有効", "", None, "有効2"], set())  # type: ignore[list-item]
        assert text.count("\n") == 1  # 2 行 = 改行 1 つ
        assert "有効" in text


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
        text, usage = generate_comment(client, "prompt", set(), sleep_fn=lambda _: None)
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
        text, usage = generate_comment(client, "prompt", set(), sleep_fn=lambda _: None)
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
            generate_comment(client, "prompt", set(), sleep_fn=lambda _: None)
        assert "文字数不正" in str(excinfo.value) or "行数不正" in str(excinfo.value)
        assert client.models.generate_content.call_count == 3

    def test_raises_gemini_call_error(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("network down")
        with pytest.raises(GeminiCallError):
            generate_comment(client, "prompt", set(), sleep_fn=lambda _: None)

    def test_validates_against_pii(self):
        """PII リークコメントは検証 NG → 再生成"""
        leak = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "今月は山田太郎さんの活動が顕著で、補助活動も伸びている状況が見られます。\n"
            "来月以降も予算進捗の中間モニタリングを継続し、早期の乖離検知を推奨します。"
        )
        client = self._mock_client([
            self._mock_response(leak),
            self._mock_response(VALID_COMMENT),
        ])
        text, usage = generate_comment(
            client, "prompt", {"山田太郎"}, sleep_fn=lambda _: None
        )
        assert text == VALID_COMMENT
        assert usage["attempts"] == 2

    def test_sleeps_between_attempts(self):
        slept = []
        client = self._mock_client([
            self._mock_response("短い"),
            self._mock_response(VALID_COMMENT),
        ])
        generate_comment(client, "prompt", set(), sleep_fn=lambda s: slept.append(s))
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
