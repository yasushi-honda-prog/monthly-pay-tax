"""POST /eval/team-monthly エンドポイント + team_eval_service のユニットテスト

spec: docs/specs/2026-06-10-team-budget-eval-design.md §5

外部依存（BQ / Vertex AI Gemini / Chat 通知）は全てモック。
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import team_eval_service
from main import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# -------- resolve_year_month --------


class TestResolveYearMonth:
    def test_returns_input_when_specified(self):
        assert team_eval_service.resolve_year_month(2026, 5) == (2026, 5)

    def test_resolves_prev_month_in_jst_mid_year(self):
        jst = timezone(timedelta(hours=9))
        with patch("team_eval_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 1, 7, 0, 0, tzinfo=jst)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert team_eval_service.resolve_year_month(None, None) == (2026, 5)

    def test_resolves_prev_month_jan_to_dec(self):
        jst = timezone(timedelta(hours=9))
        with patch("team_eval_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, 7, 0, 0, tzinfo=jst)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert team_eval_service.resolve_year_month(None, None) == (2025, 12)


# -------- extract_actor --------


class TestExtractActor:
    def _req(self, headers: dict):
        req = MagicMock()
        req.headers = headers
        return req

    def test_uses_iap_header(self):
        actor = team_eval_service.extract_actor(
            self._req({"X-Goog-Authenticated-User-Email": "accounts.google.com:alice@x"})
        )
        assert actor == "alice@x"

    def test_decodes_jwt_email(self):
        # JWT payload: {"email": "bob@example.com"}
        import base64, json
        payload = base64.urlsafe_b64encode(
            json.dumps({"email": "bob@example.com"}).encode()
        ).rstrip(b"=").decode()
        token = f"header.{payload}.sig"
        actor = team_eval_service.extract_actor(
            self._req({"Authorization": f"Bearer {token}"})
        )
        assert actor == "bob@example.com"

    def test_decodes_jwt_sub_when_no_email(self):
        import base64, json
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "sa:foo"}).encode()
        ).rstrip(b"=").decode()
        token = f"header.{payload}.sig"
        actor = team_eval_service.extract_actor(
            self._req({"Authorization": f"Bearer {token}"})
        )
        assert actor == "sa:foo"

    def test_returns_unknown_on_no_auth(self):
        assert team_eval_service.extract_actor(self._req({})) == "unknown"

    def test_returns_unknown_on_malformed_jwt(self):
        assert team_eval_service.extract_actor(
            self._req({"Authorization": "Bearer not.a.jwt!!"})
        ) == "unknown"


# -------- generate_job_id --------


class TestGenerateJobId:
    def test_format(self):
        job_id = team_eval_service.generate_job_id()
        assert job_id.startswith("evj-")
        # evj-YYYYMMDD-HHMMSS-<8hex>
        parts = job_id.split("-")
        assert len(parts) == 4
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 6  # HHMMSS
        assert len(parts[3]) == 8  # hex


# -------- process_one_team --------


def _make_bq_client():
    """BQ クライアントの mock。各関数の戻り値はテスト側で上書きする。"""
    return MagicMock()


VALID_COMMENT = (
    "達成率は適正範囲内で推移しており、予算策定時の想定とほぼ一致しています。\n"
    "業務の偏りも見られず、活動分類のバランスも保たれた良好な状態となっています。\n"
    "来月以降は予算進捗の中間モニタリングを実施し、早期の乖離検知を推奨します。"
)


class TestProcessOneTeam:
    @patch("team_eval_service.bq_loader.upsert_team_monthly_eval", return_value=True)
    @patch("team_eval_service.bq_loader.load_existing_eval", return_value=None)
    @patch("team_eval_service.bq_loader.release_team_eval_claim")
    @patch("team_eval_service.bq_loader.claim_team_eval_row", return_value=True)
    @patch("team_eval_service.vertex_evaluator.generate_comment",
           return_value=(VALID_COMMENT, {"prompt_tokens": 200, "output_tokens": 80, "attempts": 1}))
    @patch("team_eval_service.vertex_evaluator.load_team_samples",
           return_value=([{"work_category": "訪問", "cnt": 3, "total_amount": 90000}], ["サンプル A"]))
    @patch("team_eval_service.vertex_evaluator.compute_actual_data_hash",
           return_value="hash-1")
    @patch("team_eval_service.load_team_aggregate")
    def test_generated_flow(self, mock_agg, *_):
        mock_agg.return_value = {
            "budget_amount": 500000.0, "actual_amount": 480000.0,
            "achievement_rate": 96.0, "diff_amount": -20000.0,
            "has_budget": True, "has_actual": True,
        }
        result = team_eval_service.process_one_team(
            bq_client=_make_bq_client(), genai_client=MagicMock(),
            year=2026, month=5, team="X", force=False,
            job_id="job-1", actor="alice", member_names=set(),
        )
        assert result["status"] == "generated"
        assert result["team"] == "X"
        assert result["ai_comment"] == VALID_COMMENT
        assert result["regen_attempts"] == 1

    @patch("team_eval_service.bq_loader.claim_team_eval_row", return_value=False)
    def test_skipped_when_claim_lost(self, _claim):
        result = team_eval_service.process_one_team(
            bq_client=_make_bq_client(), genai_client=MagicMock(),
            year=2026, month=5, team="X", force=False,
            job_id="job", actor="a", member_names=set(),
        )
        assert result["status"] == "skipped_claim"

    @patch("team_eval_service.bq_loader.release_team_eval_claim")
    @patch("team_eval_service.bq_loader.claim_team_eval_row", return_value=True)
    @patch("team_eval_service.vertex_evaluator.compute_actual_data_hash", return_value="")
    @patch("team_eval_service.load_team_aggregate")
    def test_no_actual_releases_claim(self, mock_agg, *_):
        mock_agg.return_value = {
            "budget_amount": 500000.0, "actual_amount": None,
            "achievement_rate": None, "diff_amount": None,
            "has_budget": True, "has_actual": False,
        }
        result = team_eval_service.process_one_team(
            bq_client=_make_bq_client(), genai_client=MagicMock(),
            year=2026, month=5, team="X", force=False,
            job_id="job", actor="a", member_names=set(),
        )
        assert result["status"] == "no_actual"

    @patch("team_eval_service.bq_loader.release_team_eval_claim")
    @patch("team_eval_service.bq_loader.load_existing_eval",
           return_value={"actual_data_hash": "same"})
    @patch("team_eval_service.bq_loader.claim_team_eval_row", return_value=True)
    @patch("team_eval_service.vertex_evaluator.compute_actual_data_hash", return_value="same")
    @patch("team_eval_service.load_team_aggregate")
    def test_skipped_when_hash_matches_and_not_forced(self, mock_agg, *_):
        mock_agg.return_value = {
            "budget_amount": 500000.0, "actual_amount": 480000.0,
            "achievement_rate": 96.0, "diff_amount": -20000.0,
            "has_budget": True, "has_actual": True,
        }
        result = team_eval_service.process_one_team(
            bq_client=_make_bq_client(), genai_client=MagicMock(),
            year=2026, month=5, team="X", force=False,
            job_id="job", actor="a", member_names=set(),
        )
        assert result["status"] == "skipped_hash_match"

    @patch("team_eval_service.bq_loader.upsert_team_monthly_eval", return_value=True)
    @patch("team_eval_service.bq_loader.load_existing_eval",
           return_value={"actual_data_hash": "same"})
    @patch("team_eval_service.bq_loader.claim_team_eval_row", return_value=True)
    @patch("team_eval_service.vertex_evaluator.generate_comment",
           return_value=(VALID_COMMENT, {"attempts": 1, "prompt_tokens": 1, "output_tokens": 1}))
    @patch("team_eval_service.vertex_evaluator.load_team_samples", return_value=([], []))
    @patch("team_eval_service.vertex_evaluator.compute_actual_data_hash", return_value="same")
    @patch("team_eval_service.load_team_aggregate")
    def test_force_regenerates_even_when_hash_matches(self, mock_agg, *_):
        mock_agg.return_value = {
            "budget_amount": 500000.0, "actual_amount": 480000.0,
            "achievement_rate": 96.0, "diff_amount": -20000.0,
            "has_budget": True, "has_actual": True,
        }
        result = team_eval_service.process_one_team(
            bq_client=_make_bq_client(), genai_client=MagicMock(),
            year=2026, month=5, team="X", force=True,
            job_id="job", actor="a", member_names=set(),
        )
        assert result["status"] == "generated"

    @patch("team_eval_service.bq_loader.release_team_eval_claim")
    @patch("team_eval_service.bq_loader.claim_team_eval_row", return_value=True)
    @patch("team_eval_service.vertex_evaluator.generate_comment",
           side_effect=RuntimeError("gemini down"))
    @patch("team_eval_service.vertex_evaluator.load_team_samples", return_value=([], []))
    @patch("team_eval_service.vertex_evaluator.compute_actual_data_hash", return_value="h")
    @patch("team_eval_service.bq_loader.load_existing_eval", return_value=None)
    @patch("team_eval_service.load_team_aggregate")
    def test_failed_releases_claim(self, mock_agg, *_):
        mock_agg.return_value = {
            "budget_amount": 500000.0, "actual_amount": 480000.0,
            "achievement_rate": 96.0, "diff_amount": -20000.0,
            "has_budget": True, "has_actual": True,
        }
        result = team_eval_service.process_one_team(
            bq_client=_make_bq_client(), genai_client=MagicMock(),
            year=2026, month=5, team="X", force=False,
            job_id="job", actor="a", member_names=set(),
        )
        assert result["status"] == "failed"
        assert result["error"] == "RuntimeError"


# -------- process_teams (オーケストレーション) --------


class TestProcessTeams:
    @patch("team_eval_service.pii_masker.load_member_names", return_value=set())
    @patch("team_eval_service.process_one_team")
    @patch("team_eval_service.list_active_teams", return_value=["A", "B"])
    def test_auto_lists_active_teams_when_none(self, mock_list, mock_proc, _names):
        mock_proc.side_effect = lambda **kw: {"team": kw["team"], "status": "generated"}
        result = team_eval_service.process_teams(
            year=2026, month=5, teams=None, force=False,
            actor="a", job_id="job",
            bq_client=MagicMock(), genai_client=MagicMock(),
        )
        mock_list.assert_called_once()
        assert result["summary"]["total"] == 2
        assert result["summary"]["generated"] == 2

    @patch("team_eval_service.pii_masker.load_member_names", return_value=set())
    @patch("team_eval_service.process_one_team")
    def test_summary_categorizes_statuses(self, mock_proc, _names):
        mock_proc.side_effect = [
            {"team": "A", "status": "generated"},
            {"team": "B", "status": "skipped_hash_match"},
            {"team": "C", "status": "no_actual"},
            {"team": "D", "status": "failed", "error": "x"},
        ]
        result = team_eval_service.process_teams(
            year=2026, month=5, teams=["A", "B", "C", "D"], force=False,
            actor="a", job_id="job",
            bq_client=MagicMock(), genai_client=MagicMock(),
        )
        s = result["summary"]
        assert s == {
            "total": 4, "generated": 1, "skipped_hash_match": 1,
            "skipped_claim": 0, "failed": 1, "no_actual": 1,
        }


# -------- HTTP endpoint --------


class TestEvalTeamMonthlyEndpoint:
    @patch("main.team_eval_service.process_teams")
    def test_sync_returns_200_with_summary(self, mock_proc, client):
        mock_proc.return_value = {
            "year": 2026, "month": 5, "job_id": "j", "actor": "u",
            "summary": {"total": 1, "generated": 1, "skipped_hash_match": 0,
                       "skipped_claim": 0, "failed": 0, "no_actual": 0},
            "results": [{"team": "X", "status": "generated"}],
        }
        resp = client.post("/eval/team-monthly", json={
            "year": 2026, "month": 5, "teams": ["X"], "force": False, "async": False,
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["summary"]["generated"] == 1
        assert "elapsed_sec" in body

    @patch("main.chat_notifier.notify")
    @patch("main.team_eval_service.process_teams")
    def test_async_returns_202_and_runs_in_background(self, mock_proc, mock_notify, client):
        mock_proc.return_value = {
            "year": 2026, "month": 5, "job_id": "j", "actor": "u",
            "summary": {"total": 1, "generated": 1, "skipped_hash_match": 0,
                       "skipped_claim": 0, "failed": 0, "no_actual": 0},
            "results": [],
        }
        resp = client.post("/eval/team-monthly", json={
            "year": 2026, "month": 5, "async": True,
        })
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["status"] == "accepted"
        assert body["job_id"].startswith("evj-")
        # 非同期 thread の完了を軽く待つ
        import time as _t
        for _ in range(20):
            if mock_proc.called:
                break
            _t.sleep(0.05)
        assert mock_proc.called
        # Chat 通知が呼ばれる（背景処理成功時）
        for _ in range(20):
            if mock_notify.called:
                break
            _t.sleep(0.05)
        assert mock_notify.called

    @patch("main.chat_notifier.notify_fatal")
    @patch("main.team_eval_service.process_teams", side_effect=RuntimeError("boom"))
    def test_sync_500_on_unexpected_error(self, _proc, mock_fatal, client):
        resp = client.post("/eval/team-monthly", json={"year": 2026, "month": 5})
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["status"] == "error"
        assert "boom" in body["message"]
        mock_fatal.assert_called_once()

    @patch("main.team_eval_service.process_teams")
    def test_year_month_null_resolves_to_jst_prev_month(self, mock_proc, client):
        mock_proc.return_value = {
            "year": 1, "month": 1, "job_id": "j", "actor": "u",
            "summary": {"total": 0, "generated": 0, "skipped_hash_match": 0,
                       "skipped_claim": 0, "failed": 0, "no_actual": 0},
            "results": [],
        }
        resp = client.post("/eval/team-monthly", json={"year": None, "month": None})
        assert resp.status_code == 200
        # process_teams が year/month を引数として受け取っている
        _, kwargs = mock_proc.call_args
        assert isinstance(kwargs["year"], int)
        assert 1 <= kwargs["month"] <= 12
