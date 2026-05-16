"""Tests for operations_docs page (frontmatter parsing, mermaid splitting, file listing)"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def ops_module(monkeypatch):
    """operations_docs を再 import して新鮮な状態で取得"""
    sys.modules.pop("pages.operations_docs", None)
    module = importlib.import_module("pages.operations_docs")
    return module


def test_parse_frontmatter_basic(ops_module):
    text = (
        "---\n"
        "title: テストタイトル\n"
        "date: 2026-05-16\n"
        "status: active\n"
        "tags: [運用変更, スプレッドシート]\n"
        "---\n"
        "## 本文\n"
        "line\n"
    )
    meta, body = ops_module._parse_frontmatter(text)
    assert meta["title"] == "テストタイトル"
    assert meta["date"] == "2026-05-16"
    assert meta["status"] == "active"
    assert meta["tags"] == ["運用変更", "スプレッドシート"]
    assert body.startswith("## 本文")


def test_parse_frontmatter_without_frontmatter(ops_module):
    text = "## 本文だけ\nhello\n"
    meta, body = ops_module._parse_frontmatter(text)
    assert meta == {}
    assert body == text


def test_parse_frontmatter_handles_value_with_colon(ops_module):
    text = "---\ntitle: a: b: c\ndate: 2026-05-16\n---\nbody"
    meta, _ = ops_module._parse_frontmatter(text)
    assert meta["title"] == "a: b: c"


def test_load_doc_with_fallback(ops_module, tmp_path):
    p = tmp_path / "20260516_test.md"
    p.write_text("no frontmatter body", encoding="utf-8")
    entry = ops_module._load_doc(p)
    assert entry.title == "20260516_test"  # falls back to filename stem
    assert entry.date == ""
    assert entry.status == "active"
    assert entry.tags == []
    assert entry.body == "no frontmatter body"


def test_load_doc_with_frontmatter(ops_module, tmp_path):
    p = tmp_path / "20260601_x.md"
    p.write_text(
        "---\ntitle: X\ndate: 2026-06-01\nstatus: draft\ntags: [a, b]\n---\nbody here",
        encoding="utf-8",
    )
    entry = ops_module._load_doc(p)
    assert entry.title == "X"
    assert entry.date == "2026-06-01"
    assert entry.status == "draft"
    assert entry.tags == ["a", "b"]
    assert entry.body == "body here"


def test_list_docs_sorts_by_date_desc(ops_module, tmp_path):
    (tmp_path / "20260101_old.md").write_text(
        "---\ntitle: Old\ndate: 2026-01-01\n---\n", encoding="utf-8"
    )
    (tmp_path / "20260601_new.md").write_text(
        "---\ntitle: New\ndate: 2026-06-01\n---\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        "---\ntitle: README\n---\n", encoding="utf-8"
    )

    entries = ops_module.list_docs(tmp_path)
    assert [e.title for e in entries] == ["New", "Old"]


def test_list_docs_excludes_readme_case_insensitive(ops_module, tmp_path):
    (tmp_path / "Readme.md").write_text(
        "---\ntitle: Readme\n---\n", encoding="utf-8"
    )
    (tmp_path / "20260101_doc.md").write_text(
        "---\ntitle: Doc\ndate: 2026-01-01\n---\n", encoding="utf-8"
    )
    entries = ops_module.list_docs(tmp_path)
    assert [e.title for e in entries] == ["Doc"]


def test_list_docs_returns_empty_if_dir_missing(ops_module, tmp_path):
    missing = tmp_path / "no-such-dir"
    assert ops_module.list_docs(missing) == []


def _setup_fake_layout(tmp_path):
    """テスト用の fake __file__ レイアウトを構築

    Returns: (here, local_dev_candidate, cloud_run_candidate)
    - here = <tmp>/repo/dashboard/_pages/operations_docs.py
    - local_dev_candidate = <tmp>/repo/docs/operations  (here.parents[2]/docs/operations)
    - cloud_run_candidate = <tmp>/repo/dashboard/docs/operations  (here.parents[1]/docs/operations)
    """
    here = tmp_path / "repo" / "dashboard" / "_pages" / "operations_docs.py"
    here.parent.mkdir(parents=True)
    here.touch()
    local_dev = tmp_path / "repo" / "docs" / "operations"
    cloud_run = tmp_path / "repo" / "dashboard" / "docs" / "operations"
    return here, local_dev, cloud_run


def test_resolve_docs_dir_prefers_local_dev_when_both_exist(ops_module, tmp_path, monkeypatch):
    """両候補が存在するときはローカル開発パス (parents[2]) が優先される"""
    here, local_dev, cloud_run = _setup_fake_layout(tmp_path)
    local_dev.mkdir(parents=True)
    cloud_run.mkdir(parents=True)
    monkeypatch.setattr(ops_module, "__file__", str(here))
    assert ops_module._resolve_docs_dir() == local_dev


def test_resolve_docs_dir_falls_back_to_cloud_run_when_local_missing(ops_module, tmp_path, monkeypatch):
    """ローカル開発パスがなく Cloud Run パスのみある場合は Cloud Run パスを返す"""
    here, local_dev, cloud_run = _setup_fake_layout(tmp_path)
    cloud_run.mkdir(parents=True)
    monkeypatch.setattr(ops_module, "__file__", str(here))
    assert ops_module._resolve_docs_dir() == cloud_run


def test_resolve_docs_dir_returns_first_candidate_when_none_exist(ops_module, tmp_path, monkeypatch):
    """どちらも存在しない場合は最初の候補（ローカル開発パス）を返す（list_docs 側で空扱い）"""
    here, local_dev, _ = _setup_fake_layout(tmp_path)
    monkeypatch.setattr(ops_module, "__file__", str(here))
    assert ops_module._resolve_docs_dir() == local_dev


def test_doc_entry_display_label_active(ops_module):
    entry = ops_module.DocEntry(
        path=Path("x.md"),
        title="活動分類 rename",
        date="2026-05-16",
        status="active",
        tags=[],
        body="",
    )
    assert entry.display_label == "2026-05-16  活動分類 rename"


def test_doc_entry_display_label_archived(ops_module):
    entry = ops_module.DocEntry(
        path=Path("x.md"),
        title="古いドキュメント",
        date="2025-01-01",
        status="archived",
        tags=[],
        body="",
    )
    assert "[archived]" in entry.display_label


def test_render_doc_body_splits_mermaid(ops_module, monkeypatch):
    rendered_mermaid: list[str] = []
    rendered_markdown: list[str] = []

    monkeypatch.setattr(
        ops_module, "render_mermaid",
        lambda code, height: rendered_mermaid.append(code),
    )

    fake_st = MagicMock()
    fake_st.markdown = lambda text, **kwargs: rendered_markdown.append(text)
    monkeypatch.setattr(ops_module, "st", fake_st)

    body = (
        "## 前文\n\n"
        "段落 1\n\n"
        "```mermaid\nflowchart LR\n  A --> B\n```\n\n"
        "## 中間\n\n"
        "```mermaid\nsequenceDiagram\n  A->>B: hi\n```\n\n"
        "## 後文\n"
    )
    ops_module.render_doc_body(body)

    assert len(rendered_mermaid) == 2
    assert "flowchart LR" in rendered_mermaid[0]
    assert "sequenceDiagram" in rendered_mermaid[1]
    # markdown は 前文 / 中間 / 後文 の 3 ブロック
    assert len(rendered_markdown) == 3
    assert "前文" in rendered_markdown[0]
    assert "中間" in rendered_markdown[1]
    assert "後文" in rendered_markdown[2]


def test_render_doc_body_no_mermaid(ops_module, monkeypatch):
    rendered: list[str] = []
    fake_st = MagicMock()
    fake_st.markdown = lambda text, **kwargs: rendered.append(text)
    monkeypatch.setattr(ops_module, "st", fake_st)
    monkeypatch.setattr(ops_module, "render_mermaid", lambda code, height: None)

    ops_module.render_doc_body("## 単純本文\n段落のみ")
    assert len(rendered) == 1
    assert "単純本文" in rendered[0]


def test_render_doc_body_only_mermaid(ops_module, monkeypatch):
    rendered_mermaid: list[str] = []
    rendered_markdown: list[str] = []
    fake_st = MagicMock()
    fake_st.markdown = lambda text, **kwargs: rendered_markdown.append(text)
    monkeypatch.setattr(ops_module, "st", fake_st)
    monkeypatch.setattr(
        ops_module, "render_mermaid",
        lambda code, height: rendered_mermaid.append(code),
    )

    ops_module.render_doc_body("```mermaid\nflowchart TB\n  A\n```")
    assert len(rendered_mermaid) == 1
    assert rendered_markdown == []
