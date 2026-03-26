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


class TestUpdateElementContent:
    """Tests for SessionManager.update_element_content().

    Verifies that hand-edits to draft elements persist to the checkpoint
    so exports reflect user changes (bug fix: edits were frontend-only).
    """

    @pytest.mark.asyncio
    async def test_update_element_content_modifies_checkpoint(self):
        """Edited content should persist in draft_elements."""
        from src.api.session_manager import SessionManager

        manager = await SessionManager.create(":memory:")
        try:
            # Inject a fake session with draft elements in checkpoint
            session_id = "test-edit-session"
            config = {"configurable": {"thread_id": session_id}}
            manager._sessions[session_id] = {"thread_id": session_id, "position_title": None}

            # Run graph to establish checkpoint
            async for _ in manager._graph.astream({}, config, stream_mode="values"):
                pass

            # Inject draft elements into state
            draft_elements = [
                {"name": "factor_9_work_environment", "display_name": "Factor 9", "content": "Original content", "status": "drafted"},
                {"name": "introduction", "display_name": "Introduction", "content": "Intro text", "status": "drafted"},
            ]
            await manager._graph.aupdate_state(config, {"draft_elements": draft_elements})

            # Edit factor 9
            await manager.update_element_content(session_id, "factor_9_work_environment", "User edited content")

            # Verify checkpoint has updated content
            state = await manager._graph.aget_state(config)
            elements = state.values.get("draft_elements", [])
            f9 = next(e for e in elements if e["name"] == "factor_9_work_environment")
            assert f9["content"] == "User edited content"

            # Verify other elements are untouched
            intro = next(e for e in elements if e["name"] == "introduction")
            assert intro["content"] == "Intro text"
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_update_nonexistent_element_raises(self):
        """Editing a non-existent element should raise ValueError."""
        from src.api.session_manager import SessionManager

        manager = await SessionManager.create(":memory:")
        try:
            session_id = "test-edit-missing"
            config = {"configurable": {"thread_id": session_id}}
            manager._sessions[session_id] = {"thread_id": session_id, "position_title": None}

            async for _ in manager._graph.astream({}, config, stream_mode="values"):
                pass

            draft_elements = [
                {"name": "introduction", "display_name": "Introduction", "content": "text", "status": "drafted"},
            ]
            await manager._graph.aupdate_state(config, {"draft_elements": draft_elements})

            with pytest.raises(ValueError, match="not found"):
                await manager.update_element_content(session_id, "nonexistent_element", "content")
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_update_nonexistent_session_raises(self):
        """Editing in a non-existent session should raise ValueError."""
        from src.api.session_manager import SessionManager

        manager = await SessionManager.create(":memory:")
        try:
            with pytest.raises(ValueError, match="not found"):
                await manager.update_element_content("fake-session", "intro", "content")
        finally:
            await manager.close()


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
