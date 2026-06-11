"""dashboard/lib/team_hierarchy_repo.py の単体テスト。

BQ client は MagicMock で差し替え。SQL 文字列とパラメータの検証 + 戻り値の確認。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from lib import team_hierarchy_repo as repo


# --- fetch_hierarchy ---


def test_fetch_hierarchy_calls_bq_and_returns_dataframe():
    client = MagicMock()
    expected_df = pd.DataFrame({
        "activity_category": ["タダスク", "広報"],
        "leader_team": ["A", "B"],
        "leader_team_type": ["operating", "operating"],
        "note": [None, None],
        "version": [1, 1],
        "updated_at": [None, None],
        "updated_by": ["x", "y"],
    })
    job = MagicMock()
    job.to_dataframe.return_value = expected_df
    client.query.return_value = job

    result = repo.fetch_hierarchy(client=client)

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2
    sql = client.query.call_args[0][0]
    assert "team_hierarchy" in sql
    assert "ORDER BY leader_team, activity_category" in sql


# --- fetch_unmapped_activity_categories ---


def test_fetch_unmapped_filters_status_unmapped():
    client = MagicMock()
    expected_df = pd.DataFrame({"activity_category": ["X 隊", "Y 隊", "Z 隊"]})
    job = MagicMock()
    job.to_dataframe.return_value = expected_df
    client.query.return_value = job

    result = repo.fetch_unmapped_activity_categories(client=client)

    assert len(result) == 3
    sql = client.query.call_args[0][0]
    assert "v_team_hierarchy_coverage" in sql
    assert "WHERE status = 'UNMAPPED'" in sql


# --- fetch_distinct_leader_teams ---


def test_fetch_distinct_leader_teams_returns_list():
    client = MagicMock()
    job = MagicMock()
    rows = [MagicMock(leader_team="A 統括"), MagicMock(leader_team="B 統括")]
    for r, name in zip(rows, ["A 統括", "B 統括"]):
        r.leader_team = name
    job.result.return_value = iter(rows)
    client.query.return_value = job

    result = repo.fetch_distinct_leader_teams(client=client)

    assert result == ["A 統括", "B 統括"]
    sql = client.query.call_args[0][0]
    assert "SELECT DISTINCT leader_team" in sql


# --- insert_hierarchy_row (force MERGE, UNMAPPED 補完用) ---


def test_insert_force_merge_with_upsert_semantics():
    """insert_hierarchy_row は MERGE で WHEN MATCHED / WHEN NOT MATCHED 両方を持つ。"""
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job

    affected = repo.insert_hierarchy_row(
        activity_category="タダスク",
        leader_team="A 統括",
        leader_team_type="operating",
        note=None,
        actor="admin@x",
        client=client,
    )

    assert affected == 1
    sql = client.query.call_args[0][0]
    assert "MERGE" in sql
    assert "WHEN MATCHED THEN" in sql
    assert "WHEN NOT MATCHED THEN" in sql
    # force なので expected_version パラメータは無い
    assert "version = @expected_version" not in sql
    params = client.query.call_args[1]["job_config"].query_parameters
    assert all(p.name != "expected_version" for p in params)


def test_insert_preserves_audit_fields_on_match():
    """Partial Update MUST: WHEN MATCHED で created_at / created_by が更新対象でないこと。"""
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job
    repo.insert_hierarchy_row(
        activity_category="X", leader_team="L", leader_team_type="operating",
        note=None, actor="a@x", client=client,
    )
    sql = client.query.call_args[0][0]
    matched_section = sql.split("WHEN MATCHED")[1].split("WHEN NOT MATCHED")[0]
    assert "created_at" not in matched_section
    assert "created_by" not in matched_section
    assert "leader_team = s.leader_team" in matched_section
    assert "version = t.version + 1" in matched_section


def test_insert_propagates_bq_exception():
    """BQ 例外伝播テスト (CR-M2 反映): job.result() が例外を raise したら関数も raise。"""
    client = MagicMock()
    job = MagicMock()
    job.result.side_effect = RuntimeError("BQ DML failed")
    client.query.return_value = job
    with pytest.raises(RuntimeError, match="BQ DML failed"):
        repo.insert_hierarchy_row(
            activity_category="X", leader_team="L", leader_team_type="operating",
            note=None, actor="a@x", client=client,
        )


# --- update_hierarchy_row (optimistic lock, UPDATE only, no INSERT) ---


def test_update_uses_optimistic_lock_and_update_only():
    """Codex H1 反映: UPDATE のみ実行 (INSERT branch なし、削除済み行への再作成を防止)。"""
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job

    affected = repo.update_hierarchy_row(
        activity_category="タダスク",
        leader_team="A 統括",
        leader_team_type="operating",
        note="memo",
        actor="admin@x",
        expected_version=5,
        client=client,
    )

    assert affected == 1
    sql = client.query.call_args[0][0]
    # MERGE ではなく UPDATE のみ
    assert sql.strip().startswith("UPDATE")
    assert "MERGE" not in sql
    assert "INSERT" not in sql
    assert "version = @expected_version" in sql
    params = client.query.call_args[1]["job_config"].query_parameters
    expected_version_param = next(p for p in params if p.name == "expected_version")
    assert expected_version_param.value == 5
    assert expected_version_param.type_ == "INT64"


def test_update_returns_zero_on_lock_conflict_or_deleted():
    """version 不一致 or 行削除済みは affected=0。"""
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=0)
    client.query.return_value = job

    affected = repo.update_hierarchy_row(
        activity_category="X", leader_team="L", leader_team_type="operating",
        note=None, actor="a@x", expected_version=1, client=client,
    )
    assert affected == 0


def test_update_propagates_bq_exception():
    """BQ 例外伝播テスト (CR-M2 反映)。"""
    client = MagicMock()
    job = MagicMock()
    job.result.side_effect = RuntimeError("BQ UPDATE failed")
    client.query.return_value = job
    with pytest.raises(RuntimeError, match="BQ UPDATE failed"):
        repo.update_hierarchy_row(
            activity_category="X", leader_team="L", leader_team_type="operating",
            note=None, actor="a@x", expected_version=1, client=client,
        )


def test_update_does_not_touch_audit_fields():
    """Partial Update MUST: UPDATE 句に created_at / created_by が含まれないこと。"""
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job
    repo.update_hierarchy_row(
        activity_category="X", leader_team="L", leader_team_type="operating",
        note=None, actor="a@x", expected_version=1, client=client,
    )
    sql = client.query.call_args[0][0]
    assert "created_at" not in sql
    assert "created_by" not in sql
    assert "version = version + 1" in sql
    assert "updated_by = @actor" in sql


# --- rename_leader_team ---


def test_rename_leader_team_executes_update():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=3)
    client.query.return_value = job

    affected = repo.rename_leader_team("旧名", "新名", actor="a@x", client=client)

    assert affected == 3
    sql = client.query.call_args[0][0]
    assert "UPDATE" in sql
    assert "SET leader_team = @new_name" in sql
    assert "version = version + 1" in sql
    params = client.query.call_args[1]["job_config"].query_parameters
    assert next(p for p in params if p.name == "new_name").value == "新名"
    assert next(p for p in params if p.name == "old_name").value == "旧名"


def test_rename_leader_team_rejects_empty_new_name():
    client = MagicMock()
    with pytest.raises(ValueError, match="new_name が空文字"):
        repo.rename_leader_team("旧名", "  ", actor="a@x", client=client)
    client.query.assert_not_called()


def test_rename_leader_team_noop_when_same_name():
    """新旧同じ名前なら 0 件返して BQ を呼ばない (無駄 UPDATE 防止)。"""
    client = MagicMock()
    affected = repo.rename_leader_team("同じ", "同じ", actor="a@x", client=client)
    assert affected == 0
    client.query.assert_not_called()


# --- delete_hierarchy_row ---


def test_delete_hierarchy_row_executes_delete():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=1)
    client.query.return_value = job

    affected = repo.delete_hierarchy_row("タダスク", client=client)

    assert affected == 1
    sql = client.query.call_args[0][0]
    assert sql.strip().startswith("DELETE FROM")
    params = client.query.call_args[1]["job_config"].query_parameters
    assert next(p for p in params if p.name == "activity_category").value == "タダスク"


def test_delete_hierarchy_row_returns_zero_when_no_match():
    client = MagicMock()
    job = MagicMock(num_dml_affected_rows=0)
    client.query.return_value = job
    affected = repo.delete_hierarchy_row("not_exists", client=client)
    assert affected == 0


def test_delete_hierarchy_row_propagates_bq_exception():
    """BQ 例外伝播テスト (CR-M2 反映)。"""
    client = MagicMock()
    job = MagicMock()
    job.result.side_effect = RuntimeError("BQ DELETE failed")
    client.query.return_value = job
    with pytest.raises(RuntimeError, match="BQ DELETE failed"):
        repo.delete_hierarchy_row("X", client=client)


def test_rename_leader_team_propagates_bq_exception():
    """BQ 例外伝播テスト (CR-M2 反映)。"""
    client = MagicMock()
    job = MagicMock()
    job.result.side_effect = RuntimeError("BQ rename failed")
    client.query.return_value = job
    with pytest.raises(RuntimeError, match="BQ rename failed"):
        repo.rename_leader_team("旧名", "新名", actor="a@x", client=client)
