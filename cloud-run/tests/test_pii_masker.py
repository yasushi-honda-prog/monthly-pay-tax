"""PII マスキング（pii_masker）のユニットテスト

spec: docs/specs/2026-06-10-team-budget-eval-design.md §7.3 / §7.6
"""

from unittest.mock import MagicMock

import pii_masker
from pii_masker import (
    EMAIL_RE,
    PHONE_RE,
    load_member_names,
    mask_pii,
    validate_ai_comment,
)


class TestMaskPii:
    def test_empty_text_returns_empty(self):
        assert mask_pii("", ["山田"]) == ""

    def test_no_pii_returns_unchanged(self):
        text = "今月は活動時間が増えました"
        assert mask_pii(text, ["山田", "鈴木"]) == text

    def test_replaces_member_name(self):
        text = "山田さんが訪問しました"
        assert mask_pii(text, ["山田"]) == "<MEMBER>さんが訪問しました"

    def test_replaces_email(self):
        text = "連絡先は taro@example.com です"
        assert mask_pii(text, []) == "連絡先は <EMAIL> です"

    def test_replaces_phone_with_hyphen(self):
        text = "電話は 03-1234-5678 です"
        assert mask_pii(text, []) == "電話は <PHONE> です"

    def test_replaces_mobile_phone(self):
        text = "携帯 090-1234-5678 に連絡"
        assert mask_pii(text, []) == "携帯 <PHONE> に連絡"

    def test_skips_single_char_name(self):
        """1 文字名は誤検知が大きいためマスクしない"""
        text = "健の活動報告です"
        assert mask_pii(text, ["健"]) == text

    def test_replaces_longer_name_first(self):
        """長い名前を先に置換しないと部分マッチで壊れる"""
        text = "山田太郎さんと山田さんが参加"
        result = mask_pii(text, ["山田", "山田太郎"])
        assert result == "<MEMBER>さんと<MEMBER>さんが参加"
        # "山田太郎" → <MEMBER> が先に発火する
        # その後 "山田" のみ残った箇所が <MEMBER> に置換される
        assert "山田" not in result

    def test_multiple_pii_types(self):
        text = "山田さん (taro@example.com / 090-1111-2222) 訪問"
        result = mask_pii(text, ["山田"])
        assert "<MEMBER>" in result
        assert "<EMAIL>" in result
        assert "<PHONE>" in result
        assert "山田" not in result
        assert "taro@example.com" not in result
        assert "090" not in result

    def test_ignores_empty_name_in_list(self):
        """空文字や空白だけのエントリは無視する"""
        text = "今月の活動"
        # 空文字が混入していてもエラーにならない
        assert mask_pii(text, ["", "  ", None]) == text  # type: ignore[list-item]

    def test_idempotent(self):
        """マスク済みテキストを再マスクしても変化しない"""
        original = "山田さん 03-1234-5678 taro@example.com"
        masked = mask_pii(original, ["山田"])
        twice = mask_pii(masked, ["山田"])
        assert masked == twice


class TestEmailRegex:
    def test_matches_basic(self):
        assert EMAIL_RE.search("foo@example.com")

    def test_matches_with_subdomain(self):
        assert EMAIL_RE.search("foo@mail.example.co.jp")

    def test_matches_with_plus(self):
        assert EMAIL_RE.search("foo+tag@example.com")

    def test_no_match_without_at(self):
        assert EMAIL_RE.search("foo.example.com") is None

    def test_no_match_without_tld(self):
        assert EMAIL_RE.search("foo@bar") is None


class TestPhoneRegex:
    def test_matches_landline_with_hyphen(self):
        assert PHONE_RE.search("03-1234-5678")

    def test_matches_mobile_with_hyphen(self):
        assert PHONE_RE.search("090-1234-5678")

    def test_matches_freedial(self):
        assert PHONE_RE.search("0120-123-456")

    def test_matches_no_separator(self):
        assert PHONE_RE.search("09012345678")

    def test_matches_international(self):
        assert PHONE_RE.search("+81-90-1234-5678")

    def test_no_match_short_digits(self):
        """5-9 桁は電話番号として認識しない (番地・コード番号誤マッチ防止)"""
        assert PHONE_RE.search("0-1-234") is None  # 5 桁
        assert PHONE_RE.search("0123-456") is None  # 7 桁
        assert PHONE_RE.search("0123-456-78") is None  # 9 桁

    def test_no_match_long_digits(self):
        """12 桁以上も拒否"""
        assert PHONE_RE.search("0123-4567-89012") is None  # 12 桁

    def test_does_not_mask_statistics_in_text(self):
        """統計値風の数列をマスクしない (false positive 防止)"""
        from pii_masker import mask_pii
        # '0-15%' は 3 桁 → 電話番号扱いしない
        assert mask_pii("達成率 0-15% で 203 件処理", []) == "達成率 0-15% で 203 件処理"


class TestValidateAiComment:
    def _valid_comment(self) -> str:
        """検証 OK な雛形コメント（3 行 / 100-400 字）"""
        return (
            "達成率は適正範囲内で推移しており、予算策定時の想定と概ね一致しています。\n"
            "業務の偏りも見られず、活動分類ごとのバランスも保たれた良好な状態です。\n"
            "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
        )

    def test_ok_valid_comment(self):
        ok, reason = validate_ai_comment(self._valid_comment(), set())
        assert ok is True
        assert reason == ""

    def test_ng_empty(self):
        ok, reason = validate_ai_comment("", set())
        assert ok is False
        assert reason == "empty"

    def test_ng_too_few_lines(self):
        # 1 行 → 行数不正
        text = "あ" * 150
        ok, reason = validate_ai_comment(text, set())
        assert ok is False
        assert reason.startswith("行数不正")

    def test_ng_too_many_lines(self):
        text = "\n".join(["あ" * 30] * 7)
        ok, reason = validate_ai_comment(text, set())
        assert ok is False
        assert reason.startswith("行数不正")

    def test_ng_too_short(self):
        text = "短い\nテキスト"
        ok, reason = validate_ai_comment(text, set())
        assert ok is False
        assert reason.startswith("文字数不正")

    def test_ng_too_long(self):
        text = "\n".join(["あ" * 200] * 3)
        ok, reason = validate_ai_comment(text, set())
        assert ok is False
        assert reason.startswith("文字数不正")

    def test_ng_member_leak(self):
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "今月は山田太郎さんの活動が顕著で、補助活動も伸びている状況が見られます。\n"
            "来月以降も予算進捗の中間モニタリングを継続し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text, {"山田太郎"})
        assert ok is False
        assert reason == "PIIリーク:名前"

    def test_ng_email_leak(self):
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "詳細についての連絡は info@example.com までお願いしますという記載がありました。\n"
            "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text, set())
        assert ok is False
        assert reason == "PIIリーク:メール"

    def test_ng_phone_leak(self):
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "活動先からの連絡は 03-1234-5678 まで電話してほしいという依頼が見られました。\n"
            "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text, set())
        assert ok is False
        assert reason == "PIIリーク:電話"

    def test_ignores_single_char_name_leak(self):
        """1 文字名は普通名詞と衝突するため検知しない"""
        ok, _ = validate_ai_comment(self._valid_comment(), {"健"})
        assert ok is True


class TestLoadMemberNames:
    def _mock_bq_client(self, rows: list[dict]) -> MagicMock:
        client = MagicMock()

        class _Row(dict):
            def __getitem__(self, key):
                return super().__getitem__(key)

        wrapped = [_Row(r) for r in rows]
        client.query.return_value.result.return_value = wrapped
        return client

    def test_collects_last_first_nickname_combinations(self):
        client = self._mock_bq_client([
            {"last_name": "山田", "first_name": "太郎", "nickname": "やまちゃん"},
        ])
        names = load_member_names(client)
        assert "山田" in names
        assert "太郎" in names
        assert "山田太郎" in names
        assert "山田 太郎" in names
        assert "山田　太郎" in names  # 全角スペース版
        assert "やまちゃん" in names

    def test_excludes_single_char_names(self):
        client = self._mock_bq_client([
            {"last_name": "李", "first_name": "健", "nickname": "K"},
        ])
        names = load_member_names(client)
        # 1 文字単独はマスキング対象外（誤検知防止）
        assert "李" not in names
        assert "健" not in names
        assert "K" not in names
        # 連結フルネームは 2 文字以上なので残る
        assert "李健" in names

    def test_handles_none_values(self):
        client = self._mock_bq_client([
            {"last_name": "山田", "first_name": None, "nickname": None},
            {"last_name": None, "first_name": "太郎", "nickname": None},
        ])
        names = load_member_names(client)
        assert "山田" in names
        assert "太郎" in names

    def test_handles_empty_strings(self):
        client = self._mock_bq_client([
            {"last_name": "", "first_name": "", "nickname": ""},
        ])
        names = load_member_names(client)
        assert names == set()

    def test_returns_empty_on_no_rows(self):
        client = self._mock_bq_client([])
        names = load_member_names(client)
        assert names == set()

    def test_returns_empty_on_bq_error(self):
        """BQ transient エラーで例外を伝播させずに空 set を返す
        (バッチ全体が落ちるのを避ける)"""
        client = MagicMock()
        client.query.side_effect = RuntimeError("503 transient")
        assert load_member_names(client) == set()

    def test_splits_full_name_in_last_name(self):
        """last_name 列にフルネームが入っているケース（旧データ救済）"""
        client = self._mock_bq_client([
            {"last_name": "山田 太郎", "first_name": None, "nickname": None},
        ])
        names = load_member_names(client)
        # 元の値も保持されつつ、分割した個別名も取得される
        assert "山田 太郎" in names
        assert "山田" in names
        assert "太郎" in names
