"""Tests for the PD3r FastAPI application.

Tests REST endpoints using FastAPI's TestClient (synchronous, no real LLM calls).
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

import sys
from src.api.app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "service": "pd3r"}


class TestSessionEndpoints:
    def test_get_nonexistent_session(self, client):
        resp = client.get("/sessions/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_nonexistent_session(self, client):
        resp = client.delete("/sessions/nonexistent-id")
        assert resp.status_code == 404

    def test_send_message_nonexistent_session(self, client):
        resp = client.post(
            "/sessions/nonexistent-id/message",
            json={"content": "hello"},
        )
        assert resp.status_code == 404

    def test_send_message_empty_content(self, client):
        resp = client.post(
            "/sessions/nonexistent-id/message",
            json={"content": ""},
        )
        assert resp.status_code == 422  # Pydantic validation error

    def test_get_draft_nonexistent_session(self, client):
        resp = client.get("/sessions/nonexistent-id/draft")
        assert resp.status_code == 404

    def test_export_invalid_format(self, client):
        # Need a session to test format validation, but use nonexistent for 404
        resp = client.get("/sessions/nonexistent-id/export?format=pdf")
        # Either 404 (session not found) or 400 (bad format) depending on order
        assert resp.status_code in (400, 404)


class TestExportEndpoint:
    def test_export_nonexistent_session(self, client):
        resp = client.get("/sessions/nonexistent-id/export?format=markdown")
        assert resp.status_code == 404

    def test_export_bad_format(self, client):
        # Register a fake session to test format validation
        sm = sys.modules["src.api.app"].session_manager
        sm._sessions["test-session"] = {
            "thread_id": "test-session",
            "position_title": None,
        }
        try:
            resp = client.get("/sessions/test-session/export?format=pdf")
            assert resp.status_code == 400
            assert "Format" in resp.json()["detail"]
        finally:
            sm._sessions.pop("test-session", None)


class TestExportTools:
    def test_export_to_markdown_bytes(self):
        from src.tools.export_tools import export_to_markdown_bytes

        elements = [{
            "name": "introduction",
            "display_name": "Introduction",
            "content": "Test content here",
            "status": "drafted",
        }]
        result = export_to_markdown_bytes(elements)
        assert isinstance(result, bytes)
        assert b"Test content here" in result

    def test_export_to_word_bytes(self):
        from src.tools.export_tools import export_to_word_bytes

        elements = [{
            "name": "introduction",
            "display_name": "Introduction",
            "content": "Test content here",
            "status": "drafted",
        }]
        result = export_to_word_bytes(elements)
        assert isinstance(result, bytes)
        # .docx files start with PK (zip signature)
        assert result[:2] == b"PK"
