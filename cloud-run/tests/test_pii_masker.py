"""PII マスキング (pii_masker) のユニットテスト (R5 新仕様)

spec: docs/specs/2026-06-10-team-budget-eval-design.md §7.3 / §7.6
"""

from unittest.mock import MagicMock

from pii_masker import (
    EMAIL_RE,
    PHONE_RE,
    URL_RE,
    PLACEHOLDER_RE,
    MaskResult,
    assert_no_raw_pii,
    load_member_names,
    mask_pii,
    validate_ai_comment,
)


# ==============================
# mask_pii (R5: 戻り値が MaskResult)
# ==============================


class TestMaskPii:
    def test_empty_text_returns_empty(self):
        result = mask_pii("", ["山田"])
        assert isinstance(result, MaskResult)
        assert result.masked_text == ""
        assert result.detected_names == ()
        assert result.detected_email == ()
        assert result.detected_phone == ()

    def test_no_pii_returns_unchanged(self):
        text = "今月は活動時間が増えました"
        result = mask_pii(text, ["山田", "鈴木"])
        assert result.masked_text == text
        assert result.detected_names == ()

    def test_replaces_member_name(self):
        text = "山田さんが訪問しました"
        result = mask_pii(text, ["山田"])
        assert result.masked_text == "<MEMBER>さんが訪問しました"
        assert "山田" in result.detected_names

    def test_replaces_email(self):
        text = "連絡先は taro@example.com です"
        result = mask_pii(text, [])
        assert result.masked_text == "連絡先は <EMAIL> です"
        assert "taro@example.com" in result.detected_email

    def test_replaces_phone_with_hyphen(self):
        text = "電話は 03-1234-5678 です"
        result = mask_pii(text, [])
        assert result.masked_text == "電話は <PHONE> です"
        assert "03-1234-5678" in result.detected_phone

    def test_replaces_mobile_phone(self):
        text = "携帯 090-1234-5678 に連絡"
        result = mask_pii(text, [])
        assert result.masked_text == "携帯 <PHONE> に連絡"
        assert "090-1234-5678" in result.detected_phone

    def test_skips_single_char_name(self):
        """1 文字名は誤検知が大きいためマスクしない"""
        text = "健の活動報告です"
        result = mask_pii(text, ["健"])
        assert result.masked_text == text
        assert result.detected_names == ()

    def test_replaces_longer_name_first(self):
        """長い名前を先に置換しないと部分マッチで壊れる"""
        text = "山田太郎さんと山田さんが参加"
        result = mask_pii(text, ["山田", "山田太郎"])
        assert result.masked_text == "<MEMBER>さんと<MEMBER>さんが参加"
        assert "山田" not in result.masked_text
        # 長い順に置換が走るので detected_names には両方含まれる
        assert "山田太郎" in result.detected_names
        # 短い「山田」も残った箇所で hit → detected_names に含まれる
        assert "山田" in result.detected_names

    def test_multiple_pii_types(self):
        text = "山田さん (taro@example.com / 090-1111-2222) 訪問"
        result = mask_pii(text, ["山田"])
        assert "<MEMBER>" in result.masked_text
        assert "<EMAIL>" in result.masked_text
        assert "<PHONE>" in result.masked_text
        assert "山田" not in result.masked_text
        assert "taro@example.com" not in result.masked_text
        assert "090" not in result.masked_text
        assert "山田" in result.detected_names
        assert "taro@example.com" in result.detected_email
        assert "090-1111-2222" in result.detected_phone

    def test_ignores_empty_name_in_list(self):
        """空文字や空白だけのエントリは無視する"""
        text = "今月の活動"
        result = mask_pii(text, ["", "  ", None])  # type: ignore[list-item]
        assert result.masked_text == text
        assert result.detected_names == ()

    def test_idempotent(self):
        """マスク済みテキストを再マスクしても変化しない"""
        original = "山田さん 03-1234-5678 taro@example.com"
        first = mask_pii(original, ["山田"])
        second = mask_pii(first.masked_text, ["山田"])
        assert first.masked_text == second.masked_text


# ==============================
# Email / Phone / URL / Placeholder regex
# ==============================


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
        assert PHONE_RE.search("0-1-234") is None
        assert PHONE_RE.search("0123-456") is None
        assert PHONE_RE.search("0123-456-78") is None

    def test_no_match_long_digits(self):
        assert PHONE_RE.search("0123-4567-89012") is None

    def test_does_not_mask_statistics_in_text(self):
        """統計値風の数列をマスクしない (false positive 防止)"""
        result = mask_pii("達成率 0-15% で 203 件処理", [])
        assert result.masked_text == "達成率 0-15% で 203 件処理"
        assert result.detected_phone == ()


class TestUrlRegex:
    def test_matches_http(self):
        assert URL_RE.search("詳細は http://example.com まで")

    def test_matches_https(self):
        assert URL_RE.search("詳細は https://example.com/path?q=1 まで")

    def test_no_match_without_scheme(self):
        assert URL_RE.search("example.com") is None


class TestPlaceholderRegex:
    def test_matches_member(self):
        assert PLACEHOLDER_RE.search("<MEMBER> が訪問")

    def test_matches_email(self):
        assert PLACEHOLDER_RE.search("連絡先 <EMAIL>")

    def test_matches_phone(self):
        assert PLACEHOLDER_RE.search("電話 <PHONE>")

    def test_no_match_unknown_placeholder(self):
        assert PLACEHOLDER_RE.search("<UNKNOWN>") is None


# ==============================
# validate_ai_comment (R5: member_names 引数撤廃)
# ==============================


def _valid_comment() -> str:
    """検証 OK な雛形コメント (3 行 / 100-400 字)"""
    return (
        "達成率は適正範囲内で推移しており、予算策定時の想定と概ね一致しています。\n"
        "業務の偏りも見られず、活動分類ごとのバランスも保たれた良好な状態です。\n"
        "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
    )


class TestValidateAiComment:
    def test_ok_valid_comment(self):
        ok, reason = validate_ai_comment(_valid_comment())
        assert ok is True
        assert reason == ""

    def test_ng_empty(self):
        ok, reason = validate_ai_comment("")
        assert ok is False
        assert reason == "empty"

    def test_ng_too_few_lines(self):
        text = "あ" * 150
        ok, reason = validate_ai_comment(text)
        assert ok is False
        assert reason.startswith("行数不正")

    def test_ng_too_many_lines(self):
        text = "\n".join(["あ" * 30] * 7)
        ok, reason = validate_ai_comment(text)
        assert ok is False
        assert reason.startswith("行数不正")

    def test_ng_too_short(self):
        text = "短い\nテキスト"
        ok, reason = validate_ai_comment(text)
        assert ok is False
        assert reason.startswith("文字数不正")

    def test_ng_too_long(self):
        text = "\n".join(["あ" * 200] * 3)
        ok, reason = validate_ai_comment(text)
        assert ok is False
        assert reason.startswith("文字数不正")

    def test_ng_email_leak(self):
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "詳細についての連絡は info@example.com までお願いしますという記載がありました。\n"
            "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text)
        assert ok is False
        assert reason == "PIIリーク:メール"

    def test_ng_phone_leak(self):
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "活動先からの連絡は 03-1234-5678 まで電話してほしいという依頼が見られました。\n"
            "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text)
        assert ok is False
        assert reason == "PIIリーク:電話"

    def test_ng_url_leak(self):
        """AC7: URL が AI 応答に含まれたら reject"""
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "詳細は https://example.com/team を参照ください、と案内された案件もありました。\n"
            "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text)
        assert ok is False
        assert reason == "PIIリーク:URL"

    def test_ng_placeholder_member_leak(self):
        """AC6: <MEMBER> placeholder が AI 応答に流出 → reject"""
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "今月は<MEMBER>さんの活動が顕著で、補助活動も伸びている状況が見られます。\n"
            "来月以降も予算進捗の中間モニタリングを継続し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text)
        assert ok is False
        assert reason == "プレースホルダー流出"

    def test_ng_placeholder_email_leak(self):
        """AC6: <EMAIL> placeholder が AI 応答に流出 → reject"""
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "連絡先<EMAIL>から問合せが入った件は、業務の幅を広げる契機となります。\n"
            "来月以降も予算進捗の中間モニタリングを継続し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text)
        assert ok is False
        assert reason == "プレースホルダー流出"

    def test_ng_placeholder_phone_leak(self):
        """AC6: <PHONE> placeholder が AI 応答に流出 → reject"""
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
            "電話 <PHONE> への問合せが入った件は、業務の幅を広げる契機となります。\n"
            "来月以降も予算進捗の中間モニタリングを継続し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text)
        assert ok is False
        assert reason == "プレースホルダー流出"


class TestValidateAiCommentAcceptanceCriteria:
    """Codex 提示 AC1-AC7 のうち、validate_ai_comment 単体で検証可能なものをまとめる。"""

    def test_ac1_hallucinated_common_noun_clashing_nickname_not_rejected(self):
        """AC1: nickname='クニ' が member_master にあっても、validate は member_names を
        参照しないため、Gemini 応答内の普通名詞「クニ」を reject しない。"""
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定と概ね一致しています。\n"
            "このクニの政策動向に沿った活動が継続されており、業務分類のバランスも良好です。\n"
            "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text)
        assert ok is True, f"R5 設計違反: reason={reason}"

    def test_ac4_nickname_partial_match_in_common_noun_not_rejected(self):
        """AC4: nickname と普通名詞の部分一致でも reject しない。"""
        text = (
            "達成率は適正範囲内で推移しており、予算策定時の想定と概ね一致しています。\n"
            "国家システムの方針に呼応した動きがあり、活動分類のバランスも保たれています。\n"
            "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
        )
        ok, reason = validate_ai_comment(text)
        assert ok is True, f"R5 設計違反: reason={reason}"

    def test_ac5_signature_has_no_member_names_param(self):
        """AC5: validate_ai_comment のシグネチャから member_names / exclude_substrings 撤廃。"""
        import inspect

        sig = inspect.signature(validate_ai_comment)
        assert list(sig.parameters.keys()) == ["comment"], (
            f"R5: validate_ai_comment は comment のみを引数に取るべき "
            f"(実際: {list(sig.parameters.keys())})"
        )


# ==============================
# mask_pii completeness (property-based, Codex 指摘対応)
# ==============================


class TestMaskPiiCompleteness:
    """mask_pii の完全性: detected_* が masked_text に残らないことを property-based に
    検証する (Codex 指摘: assert_no_raw_pii だけでは mask 対象外名の残存を検出不可。
    入口 mask の完全性は本テストで担保する)。
    """

    _NAME_FIXTURES = ["山田", "山田太郎", "鈴木", "佐藤花子", "クニ", "やまちゃん"]
    _EMAIL_FIXTURES = ["taro@example.com", "info+team@example.co.jp"]
    _PHONE_FIXTURES = ["03-1234-5678", "090-1234-5678", "+81-90-1234-5678"]

    def test_detected_names_never_remain_in_masked_text(self):
        """member_names に与えた名前が masked_text に残らない (placeholder に置換済)。"""
        names = set(self._NAME_FIXTURES)
        contexts = [
            "山田さんと山田太郎さんと佐藤花子さんが参加",
            "クニとやまちゃんと鈴木が同席",
            "山田太郎,佐藤花子 ご来訪",
            "やまちゃん やまちゃん 山田 (重複)",
        ]
        for text in contexts:
            result = mask_pii(text, names)
            for detected in result.detected_names:
                assert detected not in result.masked_text, (
                    f"mask 不完全: detected={detected!r} が masked_text に残存 "
                    f"(input={text!r}, masked={result.masked_text!r})"
                )

    def test_detected_emails_never_remain_in_masked_text(self):
        for email in self._EMAIL_FIXTURES:
            text = f"連絡先は {email} と {email} です"
            result = mask_pii(text, [])
            assert email in result.detected_email
            assert email not in result.masked_text, (
                f"mask 不完全: email={email!r} が masked_text に残存"
            )

    def test_detected_phones_never_remain_in_masked_text(self):
        for phone in self._PHONE_FIXTURES:
            text = f"電話 {phone} に連絡し、{phone} へも折返し"
            result = mask_pii(text, [])
            assert phone in result.detected_phone
            assert phone not in result.masked_text, (
                f"mask 不完全: phone={phone!r} が masked_text に残存"
            )

    def test_all_pii_types_together_completeness(self):
        text = (
            "山田太郎さん (taro@example.com / 090-1234-5678) が "
            "クニで佐藤花子さんと info@example.com の件を協議"
        )
        result = mask_pii(text, self._NAME_FIXTURES)
        for n in result.detected_names:
            assert n not in result.masked_text
        for e in result.detected_email:
            assert e not in result.masked_text
        for p in result.detected_phone:
            assert p not in result.masked_text


# ==============================
# assert_no_raw_pii (R5 新規)
# ==============================


class TestAssertNoRawPii:
    """assert_no_raw_pii は mask 通過済テキスト (samples_text 等) のみを scan する。
    prompt 全体を渡すと team 名 / top_categories と偶然一致して false positive する
    旧設計は撤廃済み (W7 後追い修正、evaluator HIGH 1 対応)。"""

    def test_passes_when_no_raw_pii_in_masked_output(self):
        """detected_* が masked_output にない → 例外なし"""
        mr = MaskResult(
            masked_text="<MEMBER>さんが訪問",
            detected_names=("山田",),
        )
        assert_no_raw_pii("- <MEMBER>さんが訪問", [mr])

    def test_raises_when_name_in_masked_output(self):
        """detected_name が masked_output に残っている → RuntimeError (mask 漏れ実装バグ)"""
        mr = MaskResult(masked_text="<MEMBER>", detected_names=("山田",))
        try:
            assert_no_raw_pii("- 山田さんが残っている", [mr])
            assert False, "RuntimeError が raise されるべき"
        except RuntimeError as exc:
            assert "kind=name" in str(exc)

    def test_raises_when_email_in_masked_output(self):
        mr = MaskResult(masked_text="<EMAIL>", detected_email=("taro@example.com",))
        try:
            assert_no_raw_pii("- taro@example.com が残っている", [mr])
            assert False, "RuntimeError が raise されるべき"
        except RuntimeError as exc:
            assert "kind=email" in str(exc)

    def test_raises_when_phone_in_masked_output(self):
        mr = MaskResult(masked_text="<PHONE>", detected_phone=("03-1234-5678",))
        try:
            assert_no_raw_pii("- 03-1234-5678 が残っている", [mr])
            assert False, "RuntimeError が raise されるべき"
        except RuntimeError as exc:
            assert "kind=phone" in str(exc)

    def test_error_message_has_no_raw_pii(self):
        """エラーメッセージに生 PII を含めない (長さ + hash prefix のみ)。"""
        mr = MaskResult(masked_text="", detected_names=("鈴木一郎",))
        try:
            assert_no_raw_pii("- 鈴木一郎が残っている", [mr])
            assert False
        except RuntimeError as exc:
            msg = str(exc)
            assert "鈴木一郎" not in msg
            assert "鈴木" not in msg
            assert "len=4" in msg
            assert "hash=" in msg

    def test_passes_with_empty_mask_results(self):
        """mask_results が空 → 例外なし"""
        assert_no_raw_pii("任意の masked_output", [])

    def test_handles_multiple_mask_results(self):
        """複数 description にまたがる MaskResult (build_samples_text の戻り)"""
        mr1 = MaskResult(masked_text="<MEMBER>", detected_names=("山田",))
        mr2 = MaskResult(masked_text="<EMAIL>", detected_email=("a@b.com",))
        assert_no_raw_pii("- <MEMBER>\n- <EMAIL>", [mr1, mr2])
        try:
            assert_no_raw_pii("- <MEMBER>\n- a@b.com", [mr1, mr2])
            assert False
        except RuntimeError:
            pass

    def test_does_not_false_positive_on_team_name_or_top_categories(self):
        """evaluator HIGH 1 対応: assert_no_raw_pii の scan 対象は samples_text のみ。
        team 名や top_categories (work_category) に detected_name と同じ文字列が
        出現しても、scan しないので false positive しない。

        本テストは PR #233-#241 の連鎖障害と同型の false reject を assert レイヤーに
        再導入しないことを機械的に固定する (R5 設計の根本意図)。"""
        # description「すごい施策が功を奏した」を mask 通過した結果
        mr = MaskResult(
            masked_text="今月は<MEMBER>施策が功を奏した",
            detected_names=("すごい",),
        )
        # 呼び出し側は samples_text (mask 通過済の最終形) を渡す。team 名や top_lines は
        # 渡さない。samples_text には raw「すごい」が無いので例外なし。
        samples_text = "- 今月は<MEMBER>施策が功を奏した"
        assert_no_raw_pii(samples_text, [mr])  # 例外なし

        # 仮に呼び出し側が誤って prompt 全体 (team 名「すごいシステムつくり隊」を含む)
        # を渡すと false positive する。本テストは「正しい呼び出し方をする限り false
        # positive しない」ことを担保するため samples_text 経路のみ検証。


# ==============================
# load_member_names (既存維持)
# ==============================


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
        assert "山田　太郎" in names
        assert "やまちゃん" in names

    def test_excludes_single_char_names(self):
        client = self._mock_bq_client([
            {"last_name": "李", "first_name": "健", "nickname": "K"},
        ])
        names = load_member_names(client)
        assert "李" not in names
        assert "健" not in names
        assert "K" not in names
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
        client = MagicMock()
        client.query.side_effect = RuntimeError("503 transient")
        assert load_member_names(client) == set()

    def test_splits_full_name_in_last_name(self):
        client = self._mock_bq_client([
            {"last_name": "山田 太郎", "first_name": None, "nickname": None},
        ])
        names = load_member_names(client)
        assert "山田 太郎" in names
        assert "山田" in names
        assert "太郎" in names
