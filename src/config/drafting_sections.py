"""Drafting section registry and generation tier configuration.

Defines the structure, ordering, and generation approach for each section
of a federal position description. Used by generate_element_node and
drafting_tools to determine how to produce each PD section.

Generation tiers:
- "literal": Fixed text, no LLM call needed (Factor 8, Factor 9)
- "llm": Full LLM generation required (all narrative sections)
"""

from typing import Literal


GenerationTier = Literal["literal", "llm"]

# Target word counts per section. Based on baseline from real GS-1560-13 output.
# Adjust these defaults as needed — they are guidance, not hard limits.
# QA requirement completeness always takes priority over hitting word targets.
TARGET_WORD_COUNTS: dict[str, int] = {
    "introduction": 240,
    "background": 400,
    "duties_overview": 300,
    "major_duties": 300,
    "factor_1_knowledge": 270,
    "factor_2_supervisory_controls": 270,
    "factor_3_guidelines": 260,
    "factor_4_complexity": 250,
    "factor_5_scope_effect": 260,
    "factor_6_7_contacts": 260,
    "factor_8_physical_demands": 80,
    "factor_9_work_environment": 60,
    "other_significant_factors": 260,
    # Supervisory factors
    "supervisory_factor_1_program_scope": 260,
    "supervisory_factor_2_organizational_setting": 260,
    "supervisory_factor_3_authority": 260,
    "supervisory_factor_4_contacts": 260,
    "supervisory_factor_5_work_directed": 260,
    "supervisory_factor_6_other_conditions": 260,
}

SECTION_REGISTRY: dict[str, dict] = {
    "introduction": {
        "description": "Opening narrative summarizing role context and organizational placement",
        "requires": ["position_title", "organization_hierarchy", "reports_to", "mission_text"],
        "style": "narrative",
        "prompt_key": "INTRO_PROMPT",
        "generation_tier": "llm",
    },
    "background": {
        "description": "Background section describing the organizational unit's mission, the position's purpose within the organization, the series classification context, and the grade level. Do NOT include percentage-weighted duty breakdowns — those belong in Major Duties. Focus on WHY this position exists and HOW it fits into the organization's mission.",
        "requires": ["organization_hierarchy", "position_title", "series", "grade"],
        "style": "narrative",
        "prompt_key": "BACKGROUND_PROMPT",
        "generation_tier": "llm",
    },
    "duties_overview": {
        "description": "Major duties and responsibilities overview",
        "requires": ["major_duties", "daily_activities"],
        "style": "narrative",
        "prompt_key": "MAJOR_DUTIES_PROMPT",
        "generation_tier": "llm",
    },
    "factor_1_knowledge": {
        "description": "Factor 1 - Knowledge Required by the Position",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "1",
        "prompt_key": "FACTOR_PROMPT",
        "generation_tier": "llm",
    },
    "factor_2_supervisory_controls": {
        "description": "Factor 2 - Supervisory Controls",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "2",
        "prompt_key": "FACTOR_PROMPT",
        "generation_tier": "llm",
    },
    "factor_3_guidelines": {
        "description": "Factor 3 - Guidelines",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "3",
        "prompt_key": "FACTOR_PROMPT",
        "generation_tier": "llm",
    },
    "factor_4_complexity": {
        "description": "Factor 4 - Complexity",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "4",
        "prompt_key": "FACTOR_PROMPT",
        "generation_tier": "llm",
    },
    "factor_5_scope_effect": {
        "description": "Factor 5 - Scope and Effect",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "5",
        "prompt_key": "FACTOR_PROMPT",
        "generation_tier": "llm",
    },
    "factor_6_7_contacts": {
        "description": "Factor 6 - Personal Contacts and Factor 7 - Purpose of Contacts (Combined)",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "6_7",
        "prompt_key": "FACTOR_6_7_PROMPT",
        "generation_tier": "llm",
    },
    "factor_8_physical_demands": {
        "description": "Factor 8 - Physical Demands",
        "requires": ["factor_targets"],
        "style": "predetermined_narrative",
        "factor_id": "8",
        "default_level": "8-1",
        "prompt_key": None,
        "generation_tier": "literal",
    },
    "factor_9_work_environment": {
        "description": "Factor 9 - Work Environment",
        "requires": ["factor_targets"],
        "style": "predetermined_narrative",
        "factor_id": "9",
        "default_level": "9-1",
        "prompt_key": None,
        "generation_tier": "literal",
    },
    "other_significant_factors": {
        "description": "Other Significant Factors - Customer Service, Security, Safety",
        "requires": [],
        "style": "predetermined_narrative",
        "prompt_key": None,
        "generation_tier": "literal",
    },
    # ── Supervisory (GSSG) Factors ──
    # Only included for supervisory positions. These use LLM generation with
    # interview-collected supervisory data (f1–f6 ratings + subordinate details).
    "supervisory_factor_1_program_scope": {
        "description": "GSSG Factor 1 - Program Scope and Effect: describes the scope and impact of the programs supervised, including geographic spread, complexity, and mission criticality",
        "requires": ["f1_program_scope", "supervised_employees"],
        "style": "narrative",
        "prompt_key": "SUPERVISORY_FACTOR_PROMPT",
        "generation_tier": "llm",
    },
    "supervisory_factor_2_organizational_setting": {
        "description": "GSSG Factor 2 - Organizational Setting: describes the organizational level and complexity of the unit supervised, reporting relationships, and the position's place in the hierarchy",
        "requires": ["f2_organizational_setting", "organization_hierarchy"],
        "style": "narrative",
        "prompt_key": "SUPERVISORY_FACTOR_PROMPT",
        "generation_tier": "llm",
    },
    "supervisory_factor_3_authority": {
        "description": "GSSG Factor 3 - Supervisory and Managerial Authority Exercised: describes the personnel authorities exercised including hiring, performance evaluation, discipline, training, and workload management",
        "requires": ["f3_supervisory_authorities"],
        "style": "narrative",
        "prompt_key": "SUPERVISORY_FACTOR_PROMPT",
        "generation_tier": "llm",
    },
    "supervisory_factor_4_contacts": {
        "description": "GSSG Factor 4 - Personal Contacts: describes the nature, frequency, and purpose of personal contacts in the supervisory role, including contacts with senior officials, external stakeholders, and labor organizations",
        "requires": ["f4_key_contacts"],
        "style": "narrative",
        "prompt_key": "SUPERVISORY_FACTOR_PROMPT",
        "generation_tier": "llm",
    },
    "supervisory_factor_5_work_directed": {
        "description": "GSSG Factor 5 - Difficulty of Typical Work Directed: describes the difficulty level and nature of the work performed by subordinates, including the highest grade levels supervised and complexity of assignments",
        "requires": ["f5_subordinate_details", "supervised_employees"],
        "style": "narrative",
        "prompt_key": "SUPERVISORY_FACTOR_PROMPT",
        "generation_tier": "llm",
    },
    "supervisory_factor_6_other_conditions": {
        "description": "GSSG Factor 6 - Other Conditions: describes any special or unusual supervisory conditions such as geographic dispersion, shift work, hazardous conditions, or coordination across organizational lines",
        "requires": ["f6_special_conditions"],
        "style": "narrative",
        "prompt_key": "SUPERVISORY_FACTOR_PROMPT",
        "generation_tier": "llm",
    },
}

PREDETERMINED_NARRATIVES = {
    "8": {
        "1": """The work is primarily sedentary, although some slight physical effort may be required."""
    },
    "9": {
        "1": """Work is typically performed in an adequately lighted and climate controlled office. May require occasional travel."""
    },
    "other_significant_factors": {
        "default": (
            "**Customer Service:** Delivers responsive, courteous support to customers and stakeholders; "
            "communicates technical information in plain language; balances competing priorities while meeting "
            "service levels and deadlines.\n\n"
            "**Security:** Safeguards VA information systems by adhering to cybersecurity and privacy requirements "
            "(FISMA/NIST, VA Rules of Behavior); applies least\u2011privilege and change control; promptly reports "
            "and remediates vulnerabilities and incidents.\n\n"
            "**Safety:** Maintains a safe work environment and practices safe equipment handling; follows OSHA/VA "
            "safety policies; observes ergonomic best practices and safe lifting/cabling to prevent injury and "
            "service disruption."
        ),
        "supervisory": (
            "**Customer Service:** Sets service expectations and monitors quality; resolves escalations and "
            "drives continual service improvement.\n\n"
            "**Security:** Enforces compliance with cybersecurity and privacy policies; validates privileged access, "
            "reviews change activity, and ensures corrective actions.\n\n"
            "**Safety:** Promotes a safety culture; ensures staff follow VA/OSHA requirements and safe "
            "equipment/ergonomic practices."
        ),
    },
}


def get_predetermined_narrative(factor_id: str, level: str) -> str:
    """Get predetermined narrative for factors 8 and 9."""
    return PREDETERMINED_NARRATIVES.get(factor_id, {}).get(
        level, f"Narrative for Factor {factor_id} Level {level} not found"
    )


def get_generation_tier(section_id: str) -> GenerationTier:
    """Get the generation tier for a section.

    Returns:
        "literal" - Fixed text, no LLM call needed
        "llm" - Full LLM generation required (default)
    """
    section_config = SECTION_REGISTRY.get(section_id, {})
    return section_config.get("generation_tier", "llm")


def get_sections_by_tier(tier: GenerationTier) -> list[str]:
    """Get all sections that belong to a specific generation tier."""
    return [
        section_id
        for section_id, config in SECTION_REGISTRY.items()
        if config.get("generation_tier", "llm") == tier
    ]


__all__ = [
    "SECTION_REGISTRY",
    "TARGET_WORD_COUNTS",
    "GenerationTier",
    "PREDETERMINED_NARRATIVES",
    "get_predetermined_narrative",
    "get_generation_tier",
    "get_sections_by_tier",
]
