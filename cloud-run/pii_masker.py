"""PII マスキングモジュール

業務報告の description を Vertex AI Gemini に送る前に、PII（個人情報）を
プレースホルダに置換する。設計: docs/specs/2026-06-10-team-budget-eval-design.md §7.3 / §7.6

対象 PII:
- メンバー名（member_master の last_name / first_name / nickname 由来）→ <MEMBER>
- メールアドレス → <EMAIL>
- 電話番号（日本の固定/携帯/フリーダイヤル形式） → <PHONE>

マスキング後の生成結果は validate_ai_comment() で再度 PII リークを検査し、
リークが残っていれば再生成する（spec §7.6）。
"""

import logging
import re
from typing import Iterable

logger = logging.getLogger(__name__)

# メールアドレス: ローカル部に英数 _ . - + を、ドメインは英数 . - を許容
EMAIL_RE = re.compile(r"[A-Za-z0-9._+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# 電話番号:
# - +81 を含む国際表記、または 0 始まりの国内表記
# - 区切りはハイフン / 半角空白 / 全角ハイフン / 括弧 を許容（0 個以上）
# - 数字の総桁数は 10〜11 桁（市外局番含む）
# 数字部分を全て抽出した時の桁数で post-filter する（regex 単体では桁数制約が
# 緩く、5-13 桁を許容してしまい番地・統計値が誤マッチするため）
_PHONE_RAW_RE = re.compile(
    r"(?:\+?81[-\s\(\)（）]?|0)\d{1,4}[-\s\(\)（）]?\d{1,4}[-\s\(\)（）]?\d{3,4}"
)
_PHONE_DIGIT_MIN = 10
_PHONE_DIGIT_MAX = 11


def _phone_digit_count(match_text: str) -> int:
    """マッチテキストから区切り文字を除いた純粋な数字桁数を返す。
    +81 は 0 に置き換えてカウント（国際表記 → 国内表記等価）。"""
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


PHONE_RE = _PhoneRegexProxy()

# load_member_names で取得する member_master のカラム
_MEMBER_NAME_COLUMNS = ["last_name", "first_name", "nickname"]
# 1 文字名は普通名詞と衝突する誤検知が大きいため除外（spec §7.3 と一致）
_MIN_NAME_LEN = 2


def mask_pii(text: str, member_names: Iterable[str]) -> str:
    """description から PII を <MEMBER> / <EMAIL> / <PHONE> に置換する。

    名前置換は長い順に行う（"山田太郎" を先に置換しないと "山田" だけマスクされて
    "太郎" が残るような部分マッチを防ぐ）。空文字や 1 文字の名前はスキップ。
    """
    if not text:
        return text

    # 重複と短すぎる名前を除外、長い順にソートして安全に置換
    unique_names = sorted(
        {n for n in member_names if n and len(n) >= _MIN_NAME_LEN},
        key=len,
        reverse=True,
    )
    for name in unique_names:
        text = text.replace(name, "<MEMBER>")

    text = EMAIL_RE.sub("<EMAIL>", text)
    text = PHONE_RE.sub("<PHONE>", text)
    return text


def _split_full_name(value: str) -> list[str]:
    """'山田 太郎' のように区切られたフルネーム表記を分割して個別名を返す。

    マスキング時は分割されたものも含めて長い順に置換するため、
    'last_name first_name' / 'last_name+first_name' のどちらで description に
    現れても拾えるようにする。
    """
    if not value:
        return []
    # 全角/半角スペース / 中点 / カンマで分割
    parts = re.split(r"[\s　・,，、]+", value.strip())
    return [p for p in parts if p]


def load_member_names(bq_client) -> set[str]:
    """member_master からマスキング対象の名前一覧を取得する。

    取得対象:
    - last_name + first_name の連結（"山田太郎"）
    - last_name + " " + first_name（"山田 太郎"）
    - last_name 単独（苗字のみで呼ばれるケース）
    - first_name 単独（下の名前のみで呼ばれるケース）
    - nickname

    1 文字の名前は誤検知が大きいため呼び出し側 (mask_pii) で除外。
    BQ エラー時は空 set を返す（transient 失敗で 1 隊単位ではなくバッチ全体が
    落ちるのを避けるため）。マスキングなしで Gemini に送るのは PII リスクが
    あるため、呼び出し側は空 set 時に処理スキップを判断する。
    """
    import config  # 循環インポート回避のため関数内 import

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
            names.add(f"{last}　{first}")  # 全角スペース
        if nick:
            names.add(nick)

    # 空文字と 1 文字を除外
    return {n for n in names if n and len(n) >= _MIN_NAME_LEN}


def validate_ai_comment(
    comment: str,
    member_names: set[str],
    *,
    exclude_substrings: Iterable[str] = (),
) -> tuple[bool, str]:
    """Gemini が生成したコメントを検証する（spec §7.6）。

    Args:
        exclude_substrings: 隊名・統括隊名等の文脈で許容する文字列。これらの
            内部に含まれる member_names エントリは PII リーク判定から除外する。

            例: 隊名「すごいシステムつくり隊」を渡せば、nickname「すごい」が
            member_master に登録されていても、隊名内に内包されているため
            応答コメント内の「すごい」出現は PII リーク扱いしない。
            隊名は組織情報 (公開) なので除外対象として安全。本物の人名
            (例: 隊名と無関係の苗字「田中」が応答に漏れた場合) は引き続き検出。

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

    # 隊名等の context 内に内包される名前は誤検知扱いとする (false positive 防止)
    context_strings = tuple(s for s in exclude_substrings if s)
    for name in member_names:
        if not name or len(name) < _MIN_NAME_LEN:
            continue
        if any(name in ctx for ctx in context_strings):
            continue
        if name in comment:
            return False, "PIIリーク:名前"
    if EMAIL_RE.search(comment):
        return False, "PIIリーク:メール"
    if PHONE_RE.search(comment):
        return False, "PIIリーク:電話"

    return True, ""
