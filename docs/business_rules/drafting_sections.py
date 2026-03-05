from typing import Dict, List, Literal, Optional

# Generation tier definitions:
# - "literal": Fixed text, no LLM call needed (Factor 8, Factor 9)
# - "procedural": Template-based generation using interview data (intro, background)
# - "llm": Full LLM generation required (duties, factors 1-7)
GenerationTier = Literal["literal", "procedural", "llm"]

SECTION_REGISTRY: Dict[str, Dict] = {
    "introduction": {
        "description": "Opening narrative summarizing role context and organizational placement",
        "requires": ["position_title", "organization_hierarchy", "reports_to"],
        "style": "narrative",
        "batch": "introduction_duties",
        "prompt_key": "INTRO_PROMPT",
        "generation_tier": "procedural",  # Template + interview data
    },
    
    "background": {
        "description": "Background section providing organizational context and mission alignment",
        "requires": ["organization_hierarchy", "position_title", "series", "grade"],
        "style": "narrative",
        "batch": "introduction_duties",
        "prompt_key": "BACKGROUND_PROMPT",
        "generation_tier": "procedural",  # Template + interview data
    },
    
    "duties_overview": {
        "description": "Major duties and responsibilities overview", 
        "requires": ["major_duties", "daily_activities"],
        "style": "narrative",
        "batch": "introduction_duties",
        "prompt_key": "MAJOR_DUTIES_PROMPT",
        "generation_tier": "llm",  # Requires creative synthesis
    },
    
    # FES Factors - will be generated in parallel as separate prompts
    "factor_1_knowledge": {
        "description": "Factor 1 - Knowledge Required by the Position",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "1",
        "batch": "fes_factors",
        "prompt_key": "FACTOR_PROMPT",
        "generation_tier": "llm",  # Requires creative synthesis
    },
    
    "factor_2_supervisory_controls": {
        "description": "Factor 2 - Supervisory Controls",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative", 
        "factor_id": "2",
        "batch": "fes_factors",
        "prompt_key": "FACTOR_PROMPT",
        "generation_tier": "llm",  # Requires creative synthesis
    },
    
    "factor_3_guidelines": {
        "description": "Factor 3 - Guidelines",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "3",
        "batch": "fes_factors",
        "prompt_key": "FACTOR_PROMPT",
        "generation_tier": "llm",  # Requires creative synthesis
    },
    
    "factor_4_complexity": {
        "description": "Factor 4 - Complexity",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "4",
        "batch": "fes_factors",
        "prompt_key": "FACTOR_PROMPT",
        "generation_tier": "llm",  # Requires creative synthesis
    },
    
    "factor_5_scope_effect": {
        "description": "Factor 5 - Scope and Effect",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "5",
        "batch": "fes_factors",
        "prompt_key": "FACTOR_PROMPT",
        "generation_tier": "llm",  # Requires creative synthesis
    },
    
    "factor_6_7_contacts": {
        "description": "Factor 6 - Personal Contacts and Factor 7 - Purpose of Contacts (Combined)",
        "requires": ["factor_targets", "factor_context"],
        "style": "factor_narrative",
        "factor_id": "6_7",
        "batch": "fes_factors",
        "prompt_key": "FACTOR_6_7_PROMPT",
        "generation_tier": "llm",  # Requires creative synthesis
    },
    
    "factor_8_physical_demands": {
        "description": "Factor 8 - Physical Demands",
        "requires": ["factor_targets"],
        "style": "predetermined_narrative",
        "factor_id": "8",
        "default_level": "8-1",
        "batch": "fes_factors",
        "prompt_key": None,  # Uses predetermined narrative
        "generation_tier": "literal",  # Fixed text, no LLM
    },
    
    "factor_9_work_environment": {
        "description": "Factor 9 - Work Environment", 
        "requires": ["factor_targets"],
        "style": "predetermined_narrative",
        "factor_id": "9",
        "default_level": "9-1",
        "batch": "fes_factors",
        "prompt_key": None,  # Uses predetermined narrative
        "generation_tier": "literal",  # Fixed text, no LLM
    }
}

# Predetermined narratives for Factors 8 and 9
PREDETERMINED_NARRATIVES = {
    "8": {
        "1": """The work is primarily sedentary, although some slight physical effort may be required."""
    },
    "9": {
        "1": """Work is typically performed in an adequately lighted and climate controlled office. May require occasional travel."""
    }
}

def get_drafting_batches(intake_answers: dict) -> Dict[str, List[str]]:
    """Get drafting batches for parallel execution"""
    is_supervisor = str(intake_answers.get("is_supervisor", "")).lower() in ['true', 'yes', '1']
    
    batches = {
        "introduction_duties": ["introduction", "background", "duties_overview"],
        "fes_factors": [
            "factor_1_knowledge",
            "factor_2_supervisory_controls", 
            "factor_3_guidelines",
            "factor_4_complexity",
            "factor_5_scope_effect",
            "factor_6_7_contacts",
            "factor_8_physical_demands",
            "factor_9_work_environment"
        ]
    }
    
    # Removed legacy comprehensive supervisory batch; supervisory factors now generated post-QA in dedicated node
    
    return batches

def get_sections_by_batch(batch_name: str) -> List[str]:
    """Get all sections that belong to a specific batch"""
    sections = []
    for section_id, meta in SECTION_REGISTRY.items():
        if meta.get('batch') == batch_name:
            sections.append(section_id)
    return sections

def get_predetermined_narrative(factor_id: str, level: str) -> str:
    """Get predetermined narrative for factors 8 and 9"""
    return PREDETERMINED_NARRATIVES.get(factor_id, {}).get(level, f"Narrative for Factor {factor_id} Level {level} not found")

# Legacy compatibility
def get_drafting_sequence(intake_answers: dict) -> List[str]:
    """Legacy function - returns flat sequence for backward compatibility"""
    batches = get_drafting_batches(intake_answers)
    sequence = []
    for batch_sections in batches.values():
        sequence.extend(batch_sections)
    return sequence

DEFAULT_SECTION_ORDER: List[str] = ["introduction", "background", "duties_overview"]

# Export the registry and key functions
__all__ = [
    'SECTION_REGISTRY',
    'GenerationTier',
    'PREDETERMINED_NARRATIVES',
    'get_predetermined_narrative',
    'get_drafting_batches',
    'get_drafting_sequence',
    'get_prompt_for_section',
    'get_sections_requiring_llm',
    'get_generation_tier',
    'get_sections_by_tier',
]

def get_prompt_for_section(section_id: str) -> Optional[str]:
    """Get the prompt key for a specific section"""
    section_config = SECTION_REGISTRY.get(section_id, {})
    return section_config.get("prompt_key", None)

def get_sections_requiring_llm() -> List[str]:
    """Get all sections that require LLM processing (have prompt_key)"""
    return [section_id for section_id, config in SECTION_REGISTRY.items() 
            if config.get("prompt_key") is not None]

def get_sections_by_prompt(prompt_key: str) -> List[str]:
    """Get all sections that use a specific prompt"""
    return [section_id for section_id, config in SECTION_REGISTRY.items() 
            if config.get("prompt_key") == prompt_key]


def get_generation_tier(section_id: str) -> GenerationTier:
    """
    Get the generation tier for a section.
    
    Returns:
        "literal" - Fixed text, no LLM call needed
        "procedural" - Template-based generation using interview data
        "llm" - Full LLM generation required (default)
    """
    section_config = SECTION_REGISTRY.get(section_id, {})
    return section_config.get("generation_tier", "llm")


def get_sections_by_tier(tier: GenerationTier) -> List[str]:
    """Get all sections that belong to a specific generation tier."""
    return [
        section_id for section_id, config in SECTION_REGISTRY.items()
        if config.get("generation_tier", "llm") == tier
    ]
