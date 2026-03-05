# ADR-007: No Heuristic Decision Making

**Date:** 2026-01-25  
**Status:** Accepted  
**Deciders:** David Hook

## Context

During Phase E of optimization, we discovered heuristic code making decisions that should be LLM-driven. Specifically:

1. **Element identification** in `finalize_node.py` used keyword matching to identify which draft element a user wanted to revise
2. **Field naming** in `requirements.py` suggested keyword grep patterns (`keywords: list[str]`) when QA is actually LLM-evaluated
3. **Documentation** described requirements as "MUST appear" / "MUST NOT appear" suggesting mechanical checking

This violated the spirit of ADR-005 (No Mock LLM) and ADR-006 (No Heuristic Routing).

## Decision

**All decision-making that interprets user intent or evaluates content quality MUST use LLM.**

### What IS Allowed (Data Processing)

- **Format validation**: Regex for series codes (`^\d{4}$`), grade ranges (1-15)
- **Data parsing**: Extracting numbers from strings, parsing separators
- **Type conversion**: String to int, normalizing formats
- **Structured command parsing**: Explicit approve/reject from UI buttons

### What is NOT Allowed (Decision Making)

- **User intent interpretation**: What does "make some changes" mean?
- **Element identification**: Which section is "the knowledge part"?
- **Content evaluation**: Does this draft satisfy "demonstrates independent judgment"?
- **Ambiguity resolution**: Any case where user input is unclear

### Implementation

1. **Element extraction** now uses LLM with `ElementExtractionResult` schema
2. **QA evaluation** uses LLM via `qa_review.jinja` template (was already correct)
3. **Field renamed**: `keywords` → `target_content` with alias for backward compat
4. **Documentation updated**: Clarified that "target content" is for LLM context, not grep

## Consequences

### Positive
- Consistent LLM-driven architecture
- Better handling of ambiguous user input
- No false confidence from heuristic shortcuts
- Clear mental model: if it's a judgment call, LLM handles it

### Negative
- More LLM calls (but minimal: gpt-4o-mini for element extraction)
- Tests that relied on heuristic behavior now require API key
- Slightly higher latency for element identification

### Testing Impact

Tests that exercised heuristic behavior are now marked `@skip_without_llm`:
- `test_identifies_introduction_from_message`
- `test_identifies_factor_from_message`
- `test_asks_clarification_when_element_unclear`
- `test_marks_element_for_revision`

These should be converted to VCR cassettes for deterministic CI testing.

## Related

- ADR-005: No Mock LLM Policy
- ADR-006: LLM-Driven Routing
- [heuristic_audit.md](../plans/heuristic_audit.md) - Full audit findings
