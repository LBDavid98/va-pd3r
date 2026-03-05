# Business Rules Reference Guide

This guide explains how to update PD3r's draft generation rules. Business rules control what content appears (and doesn't appear) in position descriptions.

## ⚠️ IMPORTANT: LLM-Driven Evaluation

**All QA evaluation is performed by LLM, NOT keyword matching.**

When you add requirements (FES "does" statements, exclusions, etc.), you are providing **context for the LLM evaluator**, not grep patterns. The LLM uses semantic understanding to determine if:
- Inclusion requirements: The concept/meaning is conveyed in the draft
- Exclusion requirements: The concept/meaning is absent from the draft

This means:
- Exact wording doesn't matter - equivalent expressions satisfy requirements
- The LLM judges intent, not string presence
- Complex requirements (like "demonstrates independent judgment") are properly evaluated

## Quick Reference

| File | Purpose | Update Frequency |
|------|---------|------------------|
| `fes_factor_levels.json` | FES "does" statements by factor/level | Rare - OPM standards |
| `grade_cutoff_scores.json` | Point thresholds for GS grades | Rare - OPM standards |
| `gs2210_major_duties_templates.json` | Series-specific duty templates | Moderate - policy changes |
| `drafting_sections.py` | Draft section definitions | Moderate - format changes |
| `intake_fields.py` | Interview fields and validation | Common - customer feedback |
| `other_significant_factors.json` | Factors 6-9 special handling | Rare - predetermined text |

---

## 1. FES Factor Levels (`fes_factor_levels.json`)

### Structure

```json
{
  "factors": {
    "1": {
      "name": "Knowledge Required by the Position",
      "levels": {
        "1-1": {
          "points": 50,
          "does": [
            "Knowledge of basic fact-finding techniques...",
            "Ability to communicate orally and in writing..."
          ],
          "does_not": []  // Optional: statements that MUST NOT appear
        },
        "1-2": {
          "points": 200,
          "does": [
            "Knowledge of standard procedures...",
            "<REF_PRIOR_LEVEL_DUTIES>"  // Includes 1-1's unique statements
          ]
        }
      }
    }
  }
}
```

### Key Concepts

**`does` array**: Statements that MUST appear in the draft for this factor/level.

**`does_not` array** (optional): Statements that MUST NOT appear. Use for:
- Grade-inappropriate language
- Lower-grade duty descriptions
- Terminology that signals wrong complexity level

**`<REF_PRIOR_LEVEL_DUTIES>`**: Special marker that includes the **immediate prior level's unique statements** (single-level-prior, NOT recursive). 
- Level 1-3 with this marker includes Level 1-2's unique statements
- Level 1-2's unique statements are those NOT shared with 1-1

### How to Update

**Adding a "does" statement:**
```json
"1-5": {
  "points": 750,
  "does": [
    "Existing statement...",
    "NEW: Your new requirement here",
    "<REF_PRIOR_LEVEL_DUTIES>"
  ]
}
```

**Adding exclusion rules:**
```json
"1-5": {
  "points": 750,
  "does": ["..."],
  "does_not": [
    "basic clerical procedures",  // GS-5 language shouldn't appear at GS-13
    "routine filing tasks"
  ]
}
```

### Factor 7 Note

Factor 7 uses letter-based levels (7a, 7b, 7c, 7d) instead of numbers.

### Factors 8 & 9 Warning

⚠️ **DO NOT MODIFY Factors 8 & 9**. These have predetermined narratives from OPM that must be used verbatim. The system uses `predetermined_narrative` field instead of `does` arrays.

---

## 2. Grade Cutoff Scores (`grade_cutoff_scores.json`)

Maps total FES point ranges to GS grades.

```json
{
  "cutoffs": [
    {"grade": 5, "min_points": 855, "max_points": 1100},
    {"grade": 7, "min_points": 1105, "max_points": 1350}
  ]
}
```

**Update when**: OPM changes point thresholds (extremely rare).

---

## 3. Major Duties Templates (`gs2210_major_duties_templates.json`)

Defines required duty sections and weight ranges for specific series/grade combinations.

```json
{
  "templates": {
    "2210-13": {
      "series": "2210",
      "grade": "13",
      "duty_sections": [
        {
          "title": "Systems Analysis and Design",
          "min_percent": 25,
          "max_percent": 40,
          "required_keywords": ["analysis", "design", "requirements"]
        }
      ]
    }
  }
}
```

**Update when**: 
- Adding new occupational series support
- Adjusting duty weight distributions based on HR feedback

---

## 4. Drafting Sections (`drafting_sections.py`)

Defines the structure of draft elements.

```python
DRAFT_SECTIONS = {
    "introduction": {
        "order": 1,
        "required": True,
        "max_words": 150,
        "description": "Brief overview of position"
    },
    "major_duties": {
        "order": 2,
        "required": True,
        "min_sections": 3,
        "total_weight": 100  # Must sum to 100%
    }
}
```

---

## 5. Intake Fields (`intake_fields.py`)

Defines interview questions and validation.

```python
INTAKE_FIELDS = {
    "position_title": {
        "prompt": "What is the official title of this position?",
        "required": True,
        "validation": "non_empty_string"
    },
    "is_supervisor": {
        "prompt": "Does this position have supervisory responsibilities?",
        "required": True,
        "validation": "boolean"
    }
}
```

**Update when**: 
- Customer requests new interview questions
- Changing question wording for clarity
- Adding new validation rules

---

## Adding Exclusion Rules (Advanced)

The system supports "exclusion requirements" - content that **must NOT appear** in drafts.

### Use Cases

1. **Grade-inappropriate language**: Prevent senior positions from using entry-level terminology
2. **Policy compliance**: Exclude deprecated or non-compliant phrases
3. **Quality control**: Flag overused boilerplate that should be avoided

### Where to Add Exclusions

**In FES data** (`fes_factor_levels.json`):
```json
"does_not": ["basic clerical duties", "routine processing"]
```

**In code** (for complex rules): `src/nodes/gather_draft_requirements_node.py`

### How Exclusions Work

1. `_build_fes_requirements()` creates requirements from FES data
2. Exclusion requirements have `is_exclusion=True`
3. QA tools check that exclusion keywords are ABSENT from drafts
4. Finding excluded content = QA failure

---

## Testing Changes

After updating business rules:

```bash
# Run full test suite
poetry run pytest -q

# Run specific business rules tests
poetry run pytest tests/test_unit_fes.py -v

# Test with real conversation
PD3R_TRACING=true poetry run python -m src.main
```

---

## Common Pitfalls

❌ **Don't** modify Factors 8 & 9 - they have predetermined text
❌ **Don't** assume `<REF_PRIOR_LEVEL_DUTIES>` is recursive - it only goes ONE level back
❌ **Don't** forget to run tests after changes
❌ **Don't** add exclusions without clear business justification

✅ **Do** document why you're making changes
✅ **Do** test with representative position descriptions
✅ **Do** coordinate with HR SMEs on FES changes
✅ **Do** use `does_not` for grade-inappropriate language
