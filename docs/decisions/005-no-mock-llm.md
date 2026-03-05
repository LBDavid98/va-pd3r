# ADR-005: No Mock LLM Implementations

> **Status**: Accepted  
> **Date**: 2026-01-16  
> **Decision**: All LLM-dependent nodes MUST use real LLM calls. No mock/fallback implementations permitted.

---

## Context

PD3r relies on LLM calls for intent classification, field extraction, question answering, and document generation. During initial development, "basic" fallback functions were added to allow the agent to run without API keys configured.

These fallbacks created problems:
1. **False test confidence**: Tests passed but didn't validate actual LLM integration
2. **Hidden prompt bugs**: Pattern-matching fallbacks masked issues in prompts
3. **Behavioral divergence**: Production behavior differed from test behavior
4. **Complexity**: Dual code paths required maintenance and caused confusion

---

## Decision

**Effective immediately, the following are FORBIDDEN in `src/`:**

```python
# ❌ FORBIDDEN: Pattern-matching fallback
def classify_intent_basic(user_message: str) -> IntentClassification:
    if "yes" in user_message.lower():
        return IntentClassification(primary_intent="confirm", confidence=0.8)
    ...

# ❌ FORBIDDEN: Silent exception fallback
try:
    result = await llm_call()
except Exception:
    result = basic_fallback()  # NO!

# ❌ FORBIDDEN: Environment toggle
if os.getenv("USE_LLM", "false") == "true":
    result = llm_call()
else:
    result = mock_result()  # NO!
```

**Instead, use these patterns:**

```python
# ✅ REQUIRED: Fail fast on missing API key
def _require_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise ConfigurationError(
            "OPENAI_API_KEY required. This agent does not support mock fallbacks."
        )

# ✅ REQUIRED: Always call real LLM
async def intent_classification_node_async(state: AgentState) -> dict:
    _require_api_key()
    classification = await classify_intent_with_llm(user_content, state)
    return {"last_intent": classification.primary_intent}
```

---

## Testing Without API Calls

For tests that need to run without making live API calls:

1. **VCR Cassettes**: Record real LLM responses once, replay from cassette
2. **Integration test markers**: Mark tests requiring API as `@pytest.mark.integration`
3. **CI environment**: Integration tests run in CI with real API keys

Example VCR setup:
```python
@pytest.mark.vcr
async def test_intent_classification():
    # First run: records real API response to cassette
    # Subsequent runs: replays from cassette
    result = await intent_classification_node_async(state)
    assert result["last_intent"] == "provide_information"
```

---

## Consequences

### Positive
- Tests validate actual production behavior
- Prompt bugs caught immediately in development
- Single code path simplifies maintenance
- No confusion about which path is executing

### Negative
- Requires API key for most tests
- Initial cassette recording requires real API calls
- Slightly slower CI if cassettes expire

### Mitigations
- Use pytest-vcr for automatic cassette management
- Cache cassettes in git for reproducibility
- Separate unit tests (no API) from integration tests (API required)

---

## Affected Code

Nodes that MUST use real LLM (no fallback):
- `intent_classification_node.py` - Intent classification
- `answer_question_node.py` - Question answering with RAG
- `map_answers_node.py` - Field extraction
- `generate_element_node.py` - Document generation
- `qa_review_node.py` - Quality review

---

## References

- AGENTS.MD - "NO MOCK LLM POLICY" section
- docs/modules/nodes.md - Policy notice at top
