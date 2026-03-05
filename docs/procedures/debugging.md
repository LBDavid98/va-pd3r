# Debugging with Traces

> **Last Updated**: 2026-01-14

---

## Enable Tracing

### Local Tracing

```bash
PD3R_TRACING=true poetry run python -m src.main
```

### LangSmith Cloud Tracing

```bash
# Set in .env
LANGCHAIN_API_KEY=your-key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=pd3r

poetry run python -m src.main
```

---

## Trace Output

Local traces are written to `output/logs/`:

```
output/logs/
├── 2026-01-14_10-30-45.jsonl       # Machine-readable events
└── 2026-01-14_10-30-45_readable.log # Human-readable log
```

---

## Analyze Traces

```bash
# Basic analysis
poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl

# LLM cost breakdown
poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl --costs

# Node timing
poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl --timing

# Filter by event type
poetry run python scripts/analyze_trace.py --trace output/logs/<trace>.jsonl --filter llm_call
```

---

## Trace Event Types

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `node_start` | Node execution began | `node_name`, `state_snapshot` |
| `node_end` | Node execution completed | `node_name`, `result`, `duration_ms` |
| `llm_call` | LLM API call | `model`, `prompt_tokens`, `completion_tokens`, `cost` |
| `tool_call` | Tool invocation | `tool_name`, `input`, `output` |
| `state_update` | State was updated | `updates`, `new_state` |
| `error` | Exception occurred | `error_type`, `message`, `traceback` |
| `routing` | Conditional edge decision | `source`, `destination`, `condition` |

---

## Reading JSONL Traces

```python
import json

def read_trace(path: str):
    with open(path) as f:
        for line in f:
            event = json.loads(line)
            print(f"{event['timestamp']} - {event['event_type']}: {event.get('node_name', '')}")
```

---

## Common Debugging Scenarios

### 1. Node Routing Wrong

Check routing decisions in trace:

```bash
grep "routing" output/logs/<trace>.jsonl | head
```

Look for `route_by_intent` decisions and compare `last_intent` value.

### 2. High Token Usage

Filter LLM calls and sum tokens:

```bash
poetry run python scripts/analyze_trace.py --trace <trace>.jsonl --costs
```

Check which prompts are consuming the most tokens.

### 3. State Not Updating

Compare state snapshots between `node_start` and `node_end`:

```python
# In analyze script or manually
for event in trace:
    if event["event_type"] == "node_end":
        print(f"{event['node_name']}: {event['result'].keys()}")
```

### 4. Interview Field Not Captured

Check `map_answers_node` events:

```bash
grep "map_answers" output/logs/<trace>.jsonl
```

Look at `field_mappings` in the intent classification result.

### 5. QA Review Failing

Check `qa_review` events:

```bash
grep "qa_review" output/logs/<trace>.jsonl
```

Look at `check_results` to see which requirements failed.

---

## Debug Mode

Enable full debug output:

```bash
DEBUG=true PD3R_TRACING=true poetry run python -m src.main
```

This adds verbose logging to stdout in addition to trace files.

---

## Trace File Cleanup

Traces can accumulate. Clean old traces:

```bash
# Keep last 10 traces
ls -t output/logs/*.jsonl | tail -n +11 | xargs rm -f
```
