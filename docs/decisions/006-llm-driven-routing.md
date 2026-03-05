# ADR-006: LLM-Driven Routing (No Heuristics)

**Status**: Active
**Date**: 2025-01-16
**Deciders**: Architecture Team  
**Technical Story**: Migrate from heuristic phase-routing to LLM-driven tool selection

---

## Context

The PD3r agent was built with a common anti-pattern: using LLM for intent classification but heuristic Python code for routing decisions. This creates several problems:

1. **474 lines of routing.py** with phase-based if/else logic
2. **LLM reasoning is discarded** - we classify intent then route via hardcoded rules
3. **Brittle maintenance** - every new flow requires modifying routing functions
4. **Testing complexity** - must test both LLM classification AND Python routing

The current flow:
```
User Input → LLM classifies intent → Python routes by phase/intent → Next node
```

This violates LangGraph best practices where the LLM should decide what action to take through tool selection.

---

## Decision

We will migrate to **LLM-driven routing** using LangGraph's prebuilt patterns:

1. **Tool-based actions**: Convert routing decisions to tool calls
2. **interrupt() for HITL**: Use `interrupt()` and `Command(resume=...)` for human interaction
3. **Supervisor pattern**: Coordinate specialized agents via supervisor

The target flow:
```
User Input → LLM reasons & selects tool → Tool executes → LLM reasons about result
```

---

## Consequences

### Positive
- LLM reasoning is preserved in routing decisions
- Simpler codebase (delete 400+ lines of routing.py)
- Follows LangGraph best practices
- Easier to extend with new capabilities
- Better alignment with NO MOCK LLM POLICY (routing is now LLM-driven)

### Negative
- Initial migration effort (4 weeks estimated)
- May increase LLM API calls slightly
- Requires updating existing tests

### Neutral
- Changes testing approach (test tool descriptions, not routing functions)
- May need prompt tuning for reliable tool selection

---

## Anti-Patterns to Avoid (MUST NOT)

### ❌ Heuristic Phase Routing
```python
# FORBIDDEN - This is what we're removing
def route_by_intent(state):
    if phase == "init":
        return _route_init_phase(intent)
    elif phase == "interview":
        return _route_interview_phase(intent)
```

### ❌ If/Else Based on Intent Labels
```python
# FORBIDDEN - Don't route based on classification labels
if intent == "provide_information":
    return "map_answers"
elif intent == "ask_question":
    return "answer_question"
```

### ❌ Phase State Management
```python
# FORBIDDEN - Don't manage phases manually
state["phase"] = "drafting"  # Let the workflow emerge from tool usage
```

---

## Patterns to Use (MUST)

### ✅ Tool-Based Actions
```python
# REQUIRED - Let LLM decide via tool selection
@tool
def save_field_answer(field_name: str, answer: str) -> str:
    """Save a user's answer to an interview field.
    
    Use this when the user provides information about their position.
    """
    return f"Saved {field_name}: {answer}"
```

### ✅ interrupt() for Human Approval
```python
# REQUIRED - Use interrupt() for human-in-the-loop
from langgraph.types import interrupt

def confirm_requirements(state):
    response = interrupt("Please review these requirements...")
    return {"user_response": response}
```

### ✅ create_react_agent for Simple Agents
```python
# REQUIRED - Use prebuilt agents when possible
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model="anthropic:claude-sonnet-4-20250514",
    tools=[tool1, tool2, tool3],
    prompt=system_prompt,
    checkpointer=checkpointer
)
```

### ✅ Supervisor for Multi-Agent
```python
# REQUIRED - Use supervisor for coordination
from langgraph_supervisor import create_supervisor

supervisor = create_supervisor(
    model=model,
    agents=[interview_agent, drafting_agent],
    prompt=coordinator_prompt
)
```

---

## Validation Criteria

Before merging any PR during migration:

1. [ ] No new if/else routing based on phase or intent
2. [ ] All routing decisions made via LLM tool selection
3. [ ] Human interactions use `interrupt()` pattern
4. [ ] Tests verify tool selection behavior
5. [ ] Documentation updated

---

## References

- [LangGraph Agents Documentation](https://langchain-ai.github.io/langgraph/agents/)
- [Human-in-the-Loop with interrupt()](https://langchain-ai.github.io/langgraph/agents/human-in-the-loop/)
- [Multi-Agent Supervisor](https://langchain-ai.github.io/langgraph/agents/multi-agent/)
- ADR-005: No Mock LLM Policy
- Migration Plan: docs/plans/langgraph_migration_plan.md
