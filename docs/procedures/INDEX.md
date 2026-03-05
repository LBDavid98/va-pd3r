# Procedures Index

> **Last Updated**: 2026-01-14

---

## Quick Reference Commands

### Testing
```bash
# Run all tests
poetry run pytest -q

# Run specific node tests
poetry run pytest tests/test_node_*.py -v

# Run unit tests only
poetry run pytest tests/test_unit_*.py -v

# Run with coverage
poetry run pytest --cov=src tests/
```

### Running the Agent
```bash
# Standard run
poetry run python -m src.main

# With tracing enabled
PD3R_TRACING=true poetry run python -m src.main

# Analyze traces
poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl
```

### Graph Export
```bash
# Mermaid export happens automatically
# Check output/graphs/main_graph.mmd for latest
```

---

## Adding a New Node

1. Create `src/nodes/<name>_node.py`
2. Define async function accepting `AgentState`, returning dict or `Command`
3. Export from `src/nodes/__init__.py`
4. Add to graph in `src/graphs/main_graph.py`
5. Create test in `tests/test_node_<name>.py`
6. Update `docs/modules/nodes.md`

---

## Adding a New Prompt

1. Create `src/prompts/templates/<name>.jinja`
2. Use `get_template()` helper in node
3. Document in `docs/modules/prompts.md`

---

## Creating an ADR

1. Copy template from `decisions/INDEX.md`
2. Create `decisions/NNN-<title>.md`
3. Update `decisions/INDEX.md` with new entry
---

## Quick Reference

### Run Tests
```bash
poetry run pytest -q                    # All tests
poetry run pytest tests/test_node_*.py  # Node tests only
poetry run pytest -k "fes" -v           # Tests matching pattern
```

### Enable Tracing
```bash
PD3R_TRACING=true poetry run python -m src.main
```

### Analyze Traces
```bash
poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl
```

### Export Graph
```python
from src.graphs import pd_graph
from src.graphs.export import get_mermaid_syntax
print(get_mermaid_syntax(pd_graph))
```
