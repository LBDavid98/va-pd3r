# Adding a New Node

> **Last Updated**: 2026-01-14

---

## Overview

This guide walks through adding a new node to the PD3r graph. Nodes are the building blocks of the conversation flow.

---

## Steps

### 1. Create Node File

Create a new file in `src/nodes/`:

```python
# src/nodes/my_node.py
"""My node - brief description."""

from langchain_core.messages import AIMessage

from src.models.state import AgentState


def my_node(state: AgentState) -> dict:
    """
    PURPOSE: What this node does.
    
    READS: Which state fields it uses
    WRITES: Which state fields it updates
    
    Args:
        state: Current agent state
        
    Returns:
        State updates dict
    """
    # Get data from state
    phase = state.get("phase", "init")
    
    # Do processing
    result = process_something(state)
    
    # Return state updates
    return {
        "key": "value",
        "messages": [AIMessage(content="Response to user")],
    }
```

### 2. Export from `__init__.py`

Add the node to `src/nodes/__init__.py`:

```python
from src.nodes.my_node import my_node

__all__ = [
    # ... existing nodes
    "my_node",
]
```

### 3. Add to Graph

Update `src/graphs/main_graph.py`:

```python
from src.nodes import my_node

def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)
    
    # Add the node
    builder.add_node("my_node", my_node)
    
    # Add edges
    builder.add_edge("previous_node", "my_node")
    builder.add_edge("my_node", "next_node")
    
    # Or conditional edges
    builder.add_conditional_edges(
        "my_node",
        route_my_node,
        {
            "option_a": "node_a",
            "option_b": "node_b",
        },
    )
```

### 4. Write Tests

Create test file `tests/test_node_my_node.py`:

```python
"""Tests for my_node."""

import pytest
from src.nodes import my_node
from src.models import InterviewData


def test_my_node_basic():
    """Test basic node functionality."""
    state = {
        "phase": "interview",
        "messages": [],
        "interview_data": InterviewData().model_dump(),
        "missing_fields": [],
        "fields_needing_confirmation": [],
        "should_end": False,
    }
    
    result = my_node(state)
    
    assert "key" in result
    assert result["key"] == "expected_value"


def test_my_node_edge_case():
    """Test edge case handling."""
    state = {
        "phase": "init",
        # ... minimal state
    }
    
    result = my_node(state)
    assert "messages" in result
```

### 5. Update Documentation

Add entry to `docs/modules/nodes.md`:

```markdown
#### `my_node`
Brief description of what the node does.

```python
def my_node(state: AgentState) -> dict:
    # Returns: key fields
```
```

### 6. Run Tests

```bash
# Run just your new tests
poetry run pytest tests/test_node_my_node.py -v

# Run all tests to ensure no regressions
poetry run pytest -q
```

---

## Node Patterns

### Simple State Update

```python
def simple_node(state: AgentState) -> dict:
    return {
        "field": "value",
        "messages": [AIMessage(content="...")],
    }
```

### With LLM Call

```python
from langchain_openai import ChatOpenAI
from src.prompts import get_template

def llm_node(state: AgentState) -> dict:
    llm = ChatOpenAI(model="gpt-4")
    template = get_template("my_prompt.jinja")
    
    prompt = template.render(data=state["data"])
    response = llm.invoke(prompt)
    
    return {
        "result": response.content,
        "messages": [AIMessage(content=response.content)],
    }
```

### With Command (Explicit Routing)

```python
from langgraph.types import Command

def routing_node(state: AgentState) -> Command:
    if state["condition"]:
        return Command(update={"key": "a"}, goto="node_a")
    else:
        return Command(update={"key": "b"}, goto="node_b")
```

### Async Node

```python
async def async_node(state: AgentState) -> dict:
    result = await some_async_operation()
    return {"result": result}
```

---

## Checklist

- [ ] Node file created in `src/nodes/`
- [ ] Node exported in `__init__.py`
- [ ] Node added to graph in `main_graph.py`
- [ ] Edges connected properly
- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] All tests still pass
