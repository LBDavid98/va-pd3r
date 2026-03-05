# Testing Procedures

> **Last Updated**: 2025-01-16

---

## Quick Commands

```bash
# Run all tests EXCEPT LLM tests (default)
poetry run pytest -q

# Run with verbose output
poetry run pytest -v

# Run specific test file
poetry run pytest tests/test_unit_models.py -v

# Run tests matching pattern
poetry run pytest -k "test_init" -v

# Run ONLY LLM tests (requires OPENAI_API_KEY)
poetry run pytest -m llm -v

# Run ALL tests including LLM tests
poetry run pytest -m "" -v

# Run integration tests (requires API keys)
poetry run pytest tests/test_integration_*.py -v
```

---

## LLM Test Configuration

By default, tests marked with `@pytest.mark.llm` are **skipped**. This is configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "-m 'not llm'"
markers = [
    "llm: tests that require real LLM calls (deselected by default)",
]
```

### LLM Test Files

Currently, 9 tests are marked with `@pytest.mark.llm`:

| File | Tests | Description |
|------|-------|-------------|
| `test_e2e.py` | 3 | End-to-end flow tests |
| `test_integration_rag.py` | 6 | RAG retrieval integration |

Both files include `skipif` guards for missing `OPENAI_API_KEY`.

### Running LLM Tests

```bash
# Run only LLM tests (need OPENAI_API_KEY set)
pytest -m llm -v

# Run all tests including LLM
pytest -m ""
```

---

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures, markers, .env loading
├── test_unit_models.py            # Pydantic model validation
├── test_unit_nodes.py             # Node logic tests
├── test_unit_routing.py           # Routing function tests
├── test_unit_intent.py            # Intent classification tests
├── test_unit_interview.py         # Interview data tests
├── test_unit_fes.py               # FES evaluation tests
├── test_unit_draft.py             # Draft element tests
├── test_unit_duties.py            # Duty template tests
├── test_unit_validation.py        # Validation utility tests
├── test_interview_tools.py        # Interview tools and agent tests (NEW)
├── test_node_init.py              # Init node tests
├── test_node_map_answers.py       # Map answers node tests
├── test_node_prepare_next.py      # Prepare next node tests
├── test_node_check_complete.py    # Check complete node tests
├── test_node_answer_question.py   # Answer question node tests
├── test_node_fes.py               # FES evaluation node tests
└── test_integration_foundation.py # Full flow integration tests
```

---

## Test Categories

### Unit Tests
Test individual functions and models in isolation.

```bash
poetry run pytest tests/test_unit_*.py -v
```

### Node Tests
Test individual node behavior with mock state.

```bash
poetry run pytest tests/test_node_*.py -v
```

### Integration Tests
Test full conversation flows with real LLM calls.

```bash
# Requires OPENAI_API_KEY in .env
poetry run pytest tests/test_integration_*.py -v
```

---

## Writing Tests

### Unit Test Pattern

```python
def test_model_validation():
    """Test that model validates correctly."""
    data = {"field": "value"}
    model = MyModel(**data)
    assert model.field == "value"

def test_model_rejects_invalid():
    """Test that model rejects invalid input."""
    with pytest.raises(ValidationError):
        MyModel(field="")
```

### Node Test Pattern

```python
import pytest
from src.nodes import my_node
from src.models import AgentState

def test_my_node_happy_path():
    """Test node with valid input."""
    state: AgentState = {
        "phase": "interview",
        "messages": [],
        # ... required fields
    }
    result = my_node(state)
    assert "expected_key" in result

@pytest.mark.asyncio
async def test_async_node():
    """Test async node."""
    result = await async_node(state)
    assert result["key"] == "value"
```

### Integration Test Pattern

```python
import pytest
from src.graphs import pd_graph

@pytest.mark.integration
async def test_full_flow():
    """Test complete conversation flow."""
    config = {"configurable": {"thread_id": "test-123"}}
    result = await pd_graph.ainvoke(initial_state, config)
    assert result["phase"] == "complete"
```

---

## Fixtures

Common fixtures in `conftest.py`:

```python
@pytest.fixture
def empty_interview_data():
    """Fresh InterviewData instance."""
    return InterviewData()

@pytest.fixture
def sample_state():
    """Minimal valid AgentState."""
    return {
        "phase": "interview",
        "messages": [],
        "interview_data": InterviewData().model_dump(),
        # ...
    }
```

---

## Environment Variables

Integration tests require:
- `OPENAI_API_KEY` — For LLM calls

Copy `.env.example` to `.env` and add your keys.

---

## CI/CD

Tests run automatically on:
- Pull requests
- Push to main branch

Integration tests are skipped in CI unless `OPENAI_API_KEY` is set.
