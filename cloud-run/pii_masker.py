"""PII マスキングモジュール (R5 + taint tracking 設計)

設計: docs/specs/2026-06-10-team-budget-eval-design.md §7.3 / §7.6

責務分離:
- mask_pii (入口): description 内の member_names / email / phone を placeholder 置換し、
  実際に何を mask したかを MaskResult で返す (taint tracking)
- assert_no_raw_pii (二重検証): prompt 完成後に mask_pii の検出結果が prompt に残って
  いないことを assert (実装バグ検知用 fail-safe)
- validate_ai_comment (出口): Gemini 出力の email/phone/URL/placeholder 流出と形式品質のみ
  reject。member_master 辞書照合は撤廃 (Gemini hallucination で短い nickname と
  普通名詞が偶然衝突する構造的 false reject を防ぐ)

mask_pii の完全性 (= detected_* が masked_text に残らない) は test 側 property-based
test で担保。assert_no_raw_pii は「mask 漏れ検出」ではなく「prompt 構築過程で raw PII
が他の経路から混入していないか」の fail-safe 用途。
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)

# メールアドレス: ローカル部に英数 _ . - + を、ドメインは英数 . - を許容
EMAIL_RE = re.compile(r"[A-Za-z0-9._+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# 電話番号:
# - +81 を含む国際表記、または 0 始まりの国内表記
# - 区切りはハイフン / 半角空白 / 全角ハイフン / 括弧 を許容 (0 個以上)
# - 数字の総桁数は 10〜11 桁 (市外局番含む)
_PHONE_RAW_RE = re.compile(
    r"(?:\+?81[-\s\(\)（）]?|0)\d{1,4}[-\s\(\)（）]?\d{1,4}[-\s\(\)（）]?\d{3,4}"
)
_PHONE_DIGIT_MIN = 10
_PHONE_DIGIT_MAX = 11

# URL: 連絡先 PII の代替経路として AI 応答からも reject (Codex 推奨)
URL_RE = re.compile(r"https?://[^\s　、。]+")

# マスク後の placeholder が AI 応答にそのまま流出した場合の検知 (表示品質保護)
PLACEHOLDER_RE = re.compile(r"<(MEMBER|EMAIL|PHONE)>")


def _phone_digit_count(match_text: str) -> int:
    """マッチテキストから区切り文字を除いた純粋な数字桁数を返す。
    +81 は 0 に置き換えてカウント (国際表記 → 国内表記等価)。"""
    text = match_text.replace("+81", "0")
    return sum(1 for ch in text if ch.isdigit())


class _PhoneRegexProxy:
    """re.Pattern 互換の薄いラッパー。10-11 桁の電話番号のみを認識する。"""

    def search(self, text: str):
        if not text:
            return None
        for m in _PHONE_RAW_RE.finditer(text):
            if _PHONE_DIGIT_MIN <= _phone_digit_count(m.group()) <= _PHONE_DIGIT_MAX:
                return m
        return None

    def sub(self, repl: str, text: str) -> str:
        if not text:
            return text

        def _replace(m):
            return repl if _PHONE_DIGIT_MIN <= _phone_digit_count(m.group()) <= _PHONE_DIGIT_MAX else m.group()

        return _PHONE_RAW_RE.sub(_replace, text)

    def finditer(self, text: str):
        """mask_pii で detected_phone 収集用の generator。10-11 桁 filter を適用。"""
        if not text:
            return
        for m in _PHONE_RAW_RE.finditer(text):
            if _PHONE_DIGIT_MIN <= _phone_digit_count(m.group()) <= _PHONE_DIGIT_MAX:
                yield m


PHONE_RE = _PhoneRegexProxy()

# 1 文字名は普通名詞と衝突する誤検知が大きいため除外 (spec §7.3 と一致)
_MIN_NAME_LEN = 2


@dataclass(frozen=True)
class MaskResult:
    """mask_pii の結果 (taint tracking)。

    masked_text: PII を placeholder に置換した文字列
    detected_names: 元 text に出現して mask した member_master 由来の生 name (重複なし)
    detected_email: 元 text に出現して mask した生 email アドレス
    detected_phone: 元 text に出現して mask した生 電話番号

    detected_* は assert_no_raw_pii で「prompt に raw 値が残っていないか」の二重検証に
    使う。mask_pii の完全性 (detected_* が masked_text に残らない) は property-based
    test で担保。
    """

    masked_text: str
    detected_names: tuple[str, ...] = field(default_factory=tuple)
    detected_email: tuple[str, ...] = field(default_factory=tuple)
    detected_phone: tuple[str, ...] = field(default_factory=tuple)


def mask_pii(text: str, member_names: Iterable[str]) -> MaskResult:
    """description から PII を <MEMBER> / <EMAIL> / <PHONE> に置換し MaskResult を返す。

    新仕様 (R5): 戻り値は str ではなく MaskResult。call site は `result.masked_text` で
    マスク後文字列を取り、`result.detected_*` を taint として後段の assert_no_raw_pii に
    渡す。call site は cloud-run 内で `vertex_evaluator.build_samples_text` のみ。

    名前置換は長い順に行う ("山田太郎" を先に置換しないと "山田" だけマスクされて
    "太郎" が残る部分マッチを防ぐ)。空文字や 1 文字の名前はスキップ。
    """
    if not text:
        return MaskResult(masked_text=text or "")

    detected_names: list[str] = []
    detected_email: list[str] = []
    detected_phone: list[str] = []

    unique_names = sorted(
        {n for n in member_names if n and len(n) >= _MIN_NAME_LEN},
        key=len,
        reverse=True,
    )
    working = text
    for name in unique_names:
        if name in working:
            detected_names.append(name)
            working = working.replace(name, "<MEMBER>")

    for m in EMAIL_RE.finditer(working):
        detected_email.append(m.group())
    working = EMAIL_RE.sub("<EMAIL>", working)

    for m in PHONE_RE.finditer(working):
        detected_phone.append(m.group())
    working = PHONE_RE.sub("<PHONE>", working)

    return MaskResult(
        masked_text=working,
        detected_names=tuple(detected_names),
        detected_email=tuple(detected_email),
        detected_phone=tuple(detected_phone),
    )


def _split_full_name(value: str) -> list[str]:
    """'山田 太郎' のように区切られたフルネーム表記を分割して個別名を返す。"""
    if not value:
        return []
    parts = re.split(r"[\s　・,，、]+", value.strip())
    return [p for p in parts if p]


def load_member_names(bq_client) -> set[str]:
    """member_master からマスキング対象の名前一覧を取得する (mask_pii の入力用)。

    取得対象:
    - last_name + first_name の連結 ("山田太郎")
    - last_name + " " + first_name ("山田 太郎") / 全角スペース版
    - last_name 単独 (苗字のみで呼ばれるケース)
    - first_name 単独 (下の名前のみで呼ばれるケース)
    - nickname

    1 文字の名前は誤検知が大きいため mask_pii 側で除外。
    BQ エラー時は空 set を返す (transient 失敗で 1 隊単位ではなくバッチ全体が
    落ちるのを避けるため)。マスキングなしで Gemini に送るのは PII リスクが
    あるため、呼び出し側は空 set 時に処理スキップを判断する。
    """
    import config

    table_id = f"{config.GCP_PROJECT_ID}.{config.BQ_DATASET}.{config.BQ_TABLE_MEMBER_MASTER}"
    query = f"""
        SELECT last_name, first_name, nickname
        FROM `{table_id}`
        WHERE COALESCE(last_name, first_name, nickname) IS NOT NULL
    """
    names: set[str] = set()
    try:
        rows = bq_client.query(query).result()
    except Exception as exc:  # noqa: BLE001 - transient 失敗は空 set で吸収
        logger.error("load_member_names failed (空 set で継続): %s", type(exc).__name__)
        return names

    for row in rows:
        last = (row["last_name"] or "").strip() if hasattr(row, "__getitem__") else ""
        first = (row["first_name"] or "").strip() if hasattr(row, "__getitem__") else ""
        nick = (row["nickname"] or "").strip() if hasattr(row, "__getitem__") else ""

        if last:
            names.add(last)
            names.update(_split_full_name(last))
        if first:
            names.add(first)
            names.update(_split_full_name(first))
        if last and first:
            names.add(f"{last}{first}")
            names.add(f"{last} {first}")
            names.add(f"{last}　{first}")
        if nick:
            names.add(nick)

    return {n for n in names if n and len(n) >= _MIN_NAME_LEN}


def _hash_prefix(value: str) -> str:
    """エラーログ用の short hash (個人特定不可)。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def assert_no_raw_pii(masked_output: str, mask_results: Iterable[MaskResult]) -> None:
    """mask 通過済テキストに raw PII が残っていないことを assert する fail-safe。

    呼び出し側は mask_pii の出力を組み立てた最終形 (例: build_samples_text の戻り
    samples_text) を渡す。**prompt 全体は渡さない**。

    Args:
        masked_output: mask_pii を通過した最終出力テキスト (samples_text 等)
        mask_results: 同 output を組み立てた全 MaskResult (description ごとに 1 件)

    Raises:
        RuntimeError: mask 漏れによる raw PII 残存を検知 (実装バグ)。
            メッセージは長さ + SHA256 prefix で生 PII を含めない (個人特定不可)。

    設計判断 (なぜ prompt 全体ではなく masked_output だけを scan するか):
        prompt 全体には team 名・top_categories (work_category) 等の raw 文字列が
        意図的に埋め込まれる。これら「最初からマスク対象外の領域」と member_master
        由来 name が偶然一致した場合に false positive raise してしまうのが旧設計の
        欠陥だった (PR #233-#241 の連鎖障害と同型)。本関数の責務は「mask の漏れ
        検知」のみ。team / top_categories との衝突は出口 validate_ai_comment 側で
        ハンドリングしない方針 (R5 設計、Codex セカンドオピニオン採択)。

    Note: mask_pii の完全性 (= detected_* が masked_text に残らない) は test 側
    property test (TestMaskPiiCompleteness) で担保。本 assert はそれを跨ぐ実装バグ
    (e.g., samples_text 組み立て過程で raw description を誤って混入させた、複数
    description にまたがる name の取り扱い漏れ等) を検知する fail-safe。
    """
    for mr in mask_results:
        for name in mr.detected_names:
            if name in masked_output:
                raise RuntimeError(
                    f"raw PII leaked into masked output: kind=name len={len(name)} "
                    f"hash={_hash_prefix(name)}"
                )
        for email in mr.detected_email:
            if email in masked_output:
                raise RuntimeError(
                    f"raw PII leaked into masked output: kind=email "
                    f"hash={_hash_prefix(email)}"
                )
        for phone in mr.detected_phone:
            if phone in masked_output:
                raise RuntimeError(
                    f"raw PII leaked into masked output: kind=phone "
                    f"hash={_hash_prefix(phone)}"
                )


def validate_ai_comment(comment: str) -> tuple[bool, str]:
    """Gemini が生成したコメントを検証する (R5 新仕様、spec §7.6)。

    reject 対象:
    - 空コメント / 行数不正 (2-6 範囲外) / 文字数不正 (100-400 範囲外)
    - email / phone / URL (連絡先 PII の流出)
    - <MEMBER> / <EMAIL> / <PHONE> placeholder の流出 (表示品質)

    撤廃 (旧仕様):
    - `member_names` 全件辞書照合: Gemini hallucination で短い nickname と普通名詞が
      偶然衝突する構造的 false reject を引き起こすため (PR #233-#241 連鎖障害の真因)
    - `exclude_substrings`: 上記撤廃に伴い不要

    PII 対策の主戦場は入口 mask_pii に一本化。本関数は出口の品質ゲートとして
    連絡先 PII と表示品質のみを担う。

    Returns:
        (True, "") なら検証 OK。
        (False, reason) なら検証 NG。reason は再生成時のログ用。
    """
    if not comment:
        return False, "empty"

    lines = [l for l in comment.split("\n") if l.strip()]
    if not (2 <= len(lines) <= 6):
        return False, f"行数不正:{len(lines)}"
    if not (100 <= len(comment) <= 400):
        return False, f"文字数不正:{len(comment)}"

    if EMAIL_RE.search(comment):
        return False, "PIIリーク:メール"
    if PHONE_RE.search(comment):
        return False, "PIIリーク:電話"
    if URL_RE.search(comment):
        return False, "PIIリーク:URL"
    if PLACEHOLDER_RE.search(comment):
        return False, "プレースホルダー流出"

    return True, ""
