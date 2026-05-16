"""運用ドキュメントページ

`docs/operations/*.md` を frontmatter (YAML) で解析し、
本文中の ```mermaid ブロック``` を分割してレンダリング。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from lib.mermaid_renderer import estimate_mermaid_height, render_mermaid

def _resolve_docs_dir() -> Path:
    """docs/operations ディレクトリを検索

    ローカル開発: <repo_root>/docs/operations（_pages の 2 階層上）
    Cloud Run コンテナ: /app/docs/operations（_pages の 1 階層上、deploy 時にコピー）
    存在しない場合は最初の候補を返す（list_docs 側で空リスト扱い）。
    """
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "docs" / "operations",
        here.parents[1] / "docs" / "operations",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


DOCS_DIR = _resolve_docs_dir()
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)


@dataclass
class DocEntry:
    path: Path
    title: str
    date: str
    status: str
    tags: list[str]
    body: str

    @property
    def display_label(self) -> str:
        marker = "" if self.status == "active" else f" [{self.status}]"
        return f"{self.date}  {self.title}{marker}"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Markdown 先頭の YAML frontmatter を解析し、(meta, body) を返す。

    YAML パーサ非依存の軽量実装。対応形式は以下に限定:
    - スカラー値: `key: value`（quoted不可、インラインコメント不可、複数行不可）
    - リスト値: `key: [a, b, c]` 形式のみ（角括弧なしカンマ区切り・ブロックリスト非対応）

    上記以外の YAML 機能が必要になった場合は PyYAML 導入を検討。
    フォーマット仕様は docs/operations/README.md に記載。
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    raw = match.group(1)
    body = text[match.end():]
    meta: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [v.strip() for v in value[1:-1].split(",") if v.strip()]
            meta[key] = items
        else:
            meta[key] = value
    return meta, body


def _load_doc(path: Path) -> DocEntry:
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    return DocEntry(
        path=path,
        title=meta.get("title") or path.stem,
        date=meta.get("date") or "",
        status=meta.get("status") or "active",
        tags=meta.get("tags") or [],
        body=body,
    )


def list_docs(docs_dir: Path = DOCS_DIR) -> list[DocEntry]:
    """docs/operations 配下の Markdown を読み込み、日付降順で返す。README.md は除外。"""
    if not docs_dir.exists():
        return []
    entries: list[DocEntry] = []
    for path in sorted(docs_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        try:
            entries.append(_load_doc(path))
        except Exception as e:  # pragma: no cover - 個別ファイル読み込み失敗は警告のみ
            st.warning(f"ドキュメント読み込み失敗: {path.name} ({e})")
    entries.sort(key=lambda e: e.date, reverse=True)
    return entries


def render_doc_body(body: str) -> None:
    """Markdown 本文を Mermaid ブロックで分割してレンダリング"""
    last_end = 0
    for match in MERMAID_BLOCK_RE.finditer(body):
        before = body[last_end:match.start()]
        if before.strip():
            st.markdown(before, unsafe_allow_html=True)
        code = match.group(1)
        render_mermaid(code, height=estimate_mermaid_height(code))
        last_end = match.end()
    tail = body[last_end:]
    if tail.strip():
        st.markdown(tail, unsafe_allow_html=True)


def main() -> None:
    st.header("運用ドキュメント")
    st.caption("業務報告スプレッドシートの構造変更、運用判断記録などを格納")

    docs = list_docs()
    if not docs:
        st.info(
            f"ドキュメントがありません。`{DOCS_DIR.relative_to(DOCS_DIR.parents[1])}/` に "
            "Markdown ファイルを追加してください。"
        )
        return

    labels = [doc.display_label for doc in docs]
    selected_label = st.selectbox(
        "ドキュメントを選択",
        labels,
        index=0,
        label_visibility="collapsed",
    )
    selected = docs[labels.index(selected_label)] if selected_label in labels else docs[0]

    st.subheader(selected.title)
    meta_bits = [f"作成日: {selected.date}" if selected.date else "", f"status: {selected.status}"]
    if selected.tags:
        meta_bits.append("tags: " + ", ".join(selected.tags))
    st.caption(" / ".join(b for b in meta_bits if b))
    st.divider()

    render_doc_body(selected.body)


main()
