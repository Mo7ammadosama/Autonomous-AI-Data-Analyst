"""
Tests for Autonomous Agent, Domain Templates, and Custom Reports.

Uses the shared fixtures from conftest.py (TestClient, auth_headers, uploaded_dataset).
"""

import pytest


# ─────────────────────────────────────────────────────────────────────────────
#  Sandbox tests (unit — no HTTP)
# ─────────────────────────────────────────────────────────────────────────────

class TestSandbox:
    def test_basic_execution(self):
        from services.sandbox import PythonSandbox
        sb = PythonSandbox()
        result = sb.execute("print('hello sandbox')")
        assert not result.blocked
        assert not result.timed_out
        assert "hello sandbox" in result.output

    def test_block_os_system(self):
        from services.sandbox import PythonSandbox
        sb = PythonSandbox()
        result = sb.execute("import os; os.system('echo hacked')")
        assert result.blocked
        assert "os.system" in result.block_reason.lower()

    def test_block_subprocess(self):
        from services.sandbox import PythonSandbox
        sb = PythonSandbox()
        result = sb.execute("import subprocess; subprocess.run(['ls'])")
        assert result.blocked

    def test_dataframe_injection(self):
        from services.sandbox import PythonSandbox
        import pandas as pd, io
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        csv = df.to_csv(index=False)
        sb = PythonSandbox()
        result = sb.execute("print(df.shape)", df_csv=csv)
        assert not result.blocked
        assert "(3, 2)" in result.output

    def test_error_captured(self):
        from services.sandbox import PythonSandbox
        sb = PythonSandbox()
        result = sb.execute("raise ValueError('deliberate error')")
        assert "deliberate error" in result.error

    def test_math_output(self):
        from services.sandbox import PythonSandbox
        sb = PythonSandbox()
        result = sb.execute("print(2 ** 10)")
        assert "1024" in result.output


# ─────────────────────────────────────────────────────────────────────────────
#  Domain Templates tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainTemplates:
    def test_list_all_templates(self, client, auth_headers):
        resp = client.get("/api/domain-templates", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 20   # 6 domains × 4 templates each

    def test_get_finance_domain(self, client, auth_headers):
        resp = client.get("/api/domain-templates/finance", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "p_and_l_analysis" in data
        assert "cash_flow_analysis" in data
        assert "variance_report" in data
        assert "budget_vs_actual" in data

    def test_get_single_template(self, client, auth_headers):
        resp = client.get("/api/domain-templates/retail/sales_trend", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "retail"
        assert data["name"] == "sales_trend"
        assert "required_columns" in data
        assert "analysis_steps" in data
        assert "kpis" in data

    def test_unknown_domain_404(self, client, auth_headers):
        resp = client.get("/api/domain-templates/nonexistent", headers=auth_headers)
        assert resp.status_code == 404

    def test_detect_domain_from_columns(self, client, auth_headers):
        resp = client.post(
            "/api/domain-templates/detect",
            json={"columns": ["revenue", "cost", "period", "category"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "finance"
        assert data["confidence"] > 0

    def test_all_domains_present(self, client, auth_headers):
        resp = client.get("/api/domain-templates", headers=auth_headers)
        assert resp.status_code == 200
        domains = {t["domain"] for t in resp.json()}
        expected = {"finance", "retail", "healthcare", "marketing", "hr", "operations"}
        assert expected.issubset(domains)


# ─────────────────────────────────────────────────────────────────────────────
#  Agent run tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentRuns:
    def test_start_agent_run_returns_run_id(self, client, auth_headers):
        resp = client.post(
            "/api/agent/run",
            json={"task": "Summarize the dataset statistics"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "running"

    def test_list_agent_runs(self, client, auth_headers):
        resp = client.get("/api/agent/runs", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_agent_run_details(self, client, auth_headers):
        # Start a run first
        start_resp = client.post(
            "/api/agent/run",
            json={"task": "Test task for detail retrieval"},
            headers=auth_headers,
        )
        assert start_resp.status_code == 200
        run_id = start_resp.json()["run_id"]

        get_resp = client.get(f"/api/agent/runs/{run_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == run_id
        assert data["task"] == "Test task for detail retrieval"
        assert data["status"] in ("running", "completed", "failed")

    def test_delete_agent_run(self, client, auth_headers):
        start_resp = client.post(
            "/api/agent/run",
            json={"task": "Task to be deleted"},
            headers=auth_headers,
        )
        run_id = start_resp.json()["run_id"]

        del_resp = client.delete(f"/api/agent/runs/{run_id}", headers=auth_headers)
        assert del_resp.status_code == 200

        get_resp = client.get(f"/api/agent/runs/{run_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    def test_get_nonexistent_run_404(self, client, auth_headers):
        resp = client.get("/api/agent/runs/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404

    def test_agent_run_with_domain(self, client, auth_headers):
        resp = client.post(
            "/api/agent/run",
            json={"task": "Analyse finance data", "domain": "finance"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        get_resp = client.get(f"/api/agent/runs/{run_id}", headers=auth_headers)
        assert get_resp.json()["domain"] == "finance"


# ─────────────────────────────────────────────────────────────────────────────
#  Custom Reports tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCustomReports:
    def test_create_report(self, client, auth_headers):
        resp = client.post(
            "/api/custom-reports",
            json={"name": "Test Finance Report", "domain": "finance"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Finance Report"
        assert data["status"] == "draft"
        return data["id"]

    def test_list_reports(self, client, auth_headers):
        resp = client.get("/api/custom-reports", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_report(self, client, auth_headers):
        create_resp = client.post(
            "/api/custom-reports",
            json={"name": "Report for Get Test"},
            headers=auth_headers,
        )
        report_id = create_resp.json()["id"]

        get_resp = client.get(f"/api/custom-reports/{report_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == report_id

    def test_update_report(self, client, auth_headers):
        create_resp = client.post(
            "/api/custom-reports",
            json={"name": "Old Name"},
            headers=auth_headers,
        )
        report_id = create_resp.json()["id"]

        update_resp = client.put(
            f"/api/custom-reports/{report_id}",
            json={"name": "Updated Name"},
            headers=auth_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Updated Name"

    def test_delete_report(self, client, auth_headers):
        create_resp = client.post(
            "/api/custom-reports",
            json={"name": "To Delete"},
            headers=auth_headers,
        )
        report_id = create_resp.json()["id"]

        del_resp = client.delete(f"/api/custom-reports/{report_id}", headers=auth_headers)
        assert del_resp.status_code == 200

        get_resp = client.get(f"/api/custom-reports/{report_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    def test_export_html(self, client, auth_headers):
        create_resp = client.post(
            "/api/custom-reports",
            json={
                "name": "Export Test",
                "sections": [
                    {"id": "s1", "type": "text", "title": "Summary",
                     "content": {"body": "Test content"}, "order": 0}
                ],
            },
            headers=auth_headers,
        )
        report_id = create_resp.json()["id"]

        export_resp = client.get(
            f"/api/custom-reports/{report_id}/export?fmt=html",
            headers=auth_headers,
        )
        assert export_resp.status_code == 200
        assert "text/html" in export_resp.headers["content-type"]
        assert "Export Test" in export_resp.text

    def test_create_report_from_template_pre_populates_sections(self, client, auth_headers):
        resp = client.post(
            "/api/custom-reports",
            json={
                "name": "Template Test",
                "domain": "finance",
                "template_name": "p_and_l_analysis",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        # Template has report_sections — they should be pre-populated
        assert len(data["sections"]) > 0
