# registries/intake_fields.py
"""🤖 AI AGENT GUIDANCE - Intake Field Registry

⚠️  BEFORE EDITING: Review the README file especially the design patterns section
to understand the LangGraph interrupt-native architecture and federal compliance requirements.

This module defines the comprehensive registry of intake fields used throughout
the federal position description workflow. It provides metadata, validation rules,
and sequencing information for structured data collection and quality assurance.

KEY ARCHITECTURE:
- Comprehensive field metadata with validation rules
- Type-specific field handling (string, list, dict, boolean)
- Federal compliance validation requirements
- Contextual help text for user guidance
- Structured field sequencing for logical data collection

DESIGN PATTERNS TO FOLLOW:
1. Centralized metadata: Define all field requirements in one location
2. Rich field definitions: Include prompts, help text, and validation rules
3. Type-aware processing: Support different field types appropriately
4. Federal compliance: Embed OPM standards in validation rules
5. User guidance: Provide clear help text and examples

ANTI-PATTERNS TO AVOID:
- Scattered field definitions across multiple modules
- Minimal metadata (include comprehensive field information)
- Generic validation (use field-specific federal standards)
- Poor user guidance (provide clear examples and help text)
- Hard-coded sequences (define configurable field ordering)

Used by: Intake node, validation utilities, review formatting
Dependencies: Federal job series standards, OPM validation requirements
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

class IntakeFieldConditional(BaseModel):
    """Simple conditional metadata for fields that depend on other answers."""

    depends_on: str = Field(..., description="Name of the field this one depends on")
    value: Any = Field(..., description="Value of the dependency that enables this field")


class IntakeField(BaseModel):
    """Pydantic model for a single intake field's metadata."""

    prompt: str = Field(..., description="Primary user-facing prompt for this field")
    user_guidance: Optional[str] = Field(
        default=None,
        description="Conversational guidance shown alongside the prompt",
    )
    field_type: str = Field(..., description="Logical type for the field (string, list, dict, boolean, integer, text)")
    required: bool = Field(..., description="Whether this field must be provided")
    category: str = Field(..., description="Logical grouping for UI and interview flows")
    examples: List[Any] = Field(
        default_factory=list,
        description="Example answers (terse, verbose, non-standard) for guidance and testing",
    )
    placeholder: Optional[str] = Field(
        default=None,
        description="Short hint for UI placeholders",
    )
    sequence_weight: int = Field(
        default=0,
        description="Ordering hint used to sequence fields within the intake flow",
    )
    llm_guidance: Optional[str] = Field(
        default=None,
        description="Optional additional guidance for LLM-based helpers",
    )
    validation: Dict[str, Any] | None = Field(
        default=None,
        description="Optional validation metadata such as patterns or choice lists",
    )
    conditional: Optional[IntakeFieldConditional] = Field(
        default=None,
        description="Optional condition controlling when this field is asked",
    )


# Canonical intake field registry used by the PD Writer graph.
#
# Design notes:
# - Each field includes type, prompt, user guidance, and validation hints.
# - "sequence_weight" enables deterministic ordering within phases.
# - "category" groups fields for UI and interview flows.
# - "examples" and "placeholder" support better user guidance.
# - "required" and optional "conditional" blocks support dynamic flows.

RAW_INTAKE_FIELDS: Dict[str, Dict[str, Any]] = {
    "position_title": {
        "prompt": "Enter the exact official position title (e.g., 'Data Scientist', 'Program Analyst', 'IT Specialist')",
        "user_guidance": "Let's start with the exact official title that will appear on the PD (no nicknames or informal labels).",
        "field_type": "string",
        "required": True,
        "category": "core_metadata",
        "examples": [
            "Data Scientist",
            "Senior Data Scientist leading the enterprise analytics program",
            "Data wizard for all things numbers and dashboards",
        ],
        "placeholder": "Official position title",
        "sequence_weight": 10,
        "llm_guidance": None,
    },
    
    "series": {
        "prompt": "Enter the job series code (e.g., 0343 for Management Analysis, 1550 for Computer Science)",
        "user_guidance": "Next, share the official OPM series code for this position. If you're not sure, you can look it up on the OPM/USAJOBS series tables.",
        "field_type": "string",
        "required": True,
        "category": "core_metadata",
        "examples": [
            "0343",
            "I think the position is a 0343 series",
            "The position is a Management Analyst",
        ],
        "placeholder": "a numerical response or job series title",
        "sequence_weight": 20,
    },
    
    "grade": {
        "prompt": "Enter the target GS grade level (1-15)",
        "user_guidance": "Now tell me the target GS grade (the level that reflects the ongoing duties, not a temporary detail or stretch assignment).",
        "field_type": "string",
        "required": True,
        "category": "core_metadata",
        "examples": [
            "Nine",
            "GS-9",
            "Target grade is GS‑13 based on the ongoing duties",
            "Somewhere in the 12–13 range, likely a 13",
        ],
        "placeholder": "Target GS grade (e.g., 9, 12, 13)",
        "sequence_weight": 30,
        "validation": {"choices": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"]},
    },
    
    "organization_hierarchy": {
        "prompt": "Describe your organization (e.g., 'Department of Veterans Affairs within the Veterans Health Administration, Digital Health Office' or just list the hierarchy separated by commas)",
        "user_guidance": "Great. Now list the organization from largest to smallest (Agency, Department/Bureau, Office, Division, Branch), separated by commas.",
        "field_type": "list",
        "required": True,
        "category": "context",
        "examples": [
            "Department of Veterans Affairs, Veterans Health Administration, Digital Health Office",
            "VA > VHA > Digital Health Office > Data & Analytics Division",
            "Big federal agency, central health arm, small digital team that handles analytics",
        ],
        "placeholder": "Agency, component, office, division...",
        "sequence_weight": 40,
    },
    
    "reports_to": {
        "prompt": "Enter the position title this job reports to (e.g., 'Chief Data Scientist', 'Division Director')",
        "user_guidance": "Next, what is the official title of the immediate supervisor this position reports to (no personal names)?",
        "field_type": "string",
        "required": True,
        "category": "context",
        "examples": [
            "Chief, Data Science Branch",
            "Supervisory Data Scientist who oversees the analytics branch",
            "My boss who runs the data shop (officially the branch chief)",
        ],
        "placeholder": "Supervisor's official title",
        "sequence_weight": 50,
    },
    
    "daily_activities": {
        "prompt": "DAILY ACTIVITIES (routine tasks): Provide 3-5 recurring day-to-day actions separated by commas (e.g., Analyze datasets in Python, Meet with stakeholders, Prepare technical reports)",
        "user_guidance": "Now describe 3–5 routine, day-to-day activities for this position. Separate them with commas and start each with a strong verb.",
        "field_type": "list",
        "required": True,
        "category": "duties",
        "examples": [
            "Analyze data; Meet with stakeholders; Prepare reports",
            "Analyze program datasets in Python, meet weekly with stakeholders, maintain dashboards, and draft short decision memos",
            "Fight with spreadsheets, answer ad‑hoc data questions, and put out fires in the reporting inbox",
        ],
        "placeholder": "3–5 routine activities, comma-separated",
        "sequence_weight": 60,
    },
    
    "major_duties": {
        "prompt": "MAJOR DUTIES (primary result areas): Provide 3-5 duty statements EACH with a time share (e.g., Lead enterprise data strategy 40%, Develop predictive models 30%, Stakeholder reporting & briefings 30%)",
        "user_guidance": "Next, share 3–5 higher-level duty statements, each with a percentage of time (in 10% increments) that adds up to 100%. Focus on outcomes, not small tasks.",
        "field_type": "dict",
        "required": True,
        "category": "duties",
        "examples": [
            "Lead data strategy 40%; Build dashboards 30%; Brief leadership 30%",
            "Lead enterprise data strategy and governance 40%; Develop and maintain predictive analytics products 30%; Provide executive‑level briefings and reports 30%",
            "Keep the data program moving, wrangle tools, and translate messy requests into something the team can actually deliver on (roughly split across those areas)",
        ],
        "placeholder": "Duty statement with % time for each",
        "sequence_weight": 70,
        "validation": {"total_percentage": 100},
    },
    
    "is_supervisor": {
        "prompt": "Will this position supervise other employees? (yes/no)",
        "user_guidance": "Now let me know whether this position directly supervises other employees (answer yes or no).",
        "field_type": "boolean",
        "required": True,
        "category": "supervisory_flag",
        "examples": [
            "yes",
            "Yes, this role directly supervises a small analytics team",
            "Sort of — they lead the work but don’t have formal supervisory authority",
        ],
        "placeholder": "yes or no",
        "sequence_weight": 80,
    },
    
    "supervised_employees": {
        "prompt": "List supervised employees by job title and grade (e.g., 'Data Analyst GS-12: 2; Research Assistant GS-11: 1')",
        "user_guidance": "If you answered yes to supervision, list the supervised positions as 'Job Title GS-XX: Number', separated by semicolons.",
        "field_type": "dict",
        "required": False,
        "category": "supervisory_details",
        "examples": [
            "Data Analyst GS‑12: 2; Research Assistant GS‑11: 1",
            "Two GS‑12 Data Analysts and one GS‑11 Research Assistant, all reporting directly to this position",
            "A couple of analysts and a junior person who helps with data cleanup (titles and grades still being finalized)",
        ],
        "placeholder": "Job Title GS-XX: Count; ...",
        "sequence_weight": 90,
        "conditional": {"depends_on": "is_supervisor", "value": True},
    },
    
    "f1_program_scope": {
        "prompt": "Rate program scope and effect factor (1-5): How broad is the scope and effect of the programs supervised?",
        "user_guidance": "For the next few questions, we’ll rate supervisory factors. First, choose a 1–5 rating for program scope and effect (1=small office/unit, 5=agency or multi-agency level).",
        "field_type": "integer",
        "required": False,
        "category": "supervisory_factors",
        "examples": [
            4,
            "I’d rate program scope as a 4 because it covers a major subdivision with visible impact",
            "The work touches a lot of people but isn’t quite agency‑wide yet",
        ],
        "sequence_weight": 100,
        "conditional": {"depends_on": "is_supervisor", "value": True},
    },
    
    "f2_organizational_setting": {
        "prompt": "Rate organizational setting factor (1-5): What is the organizational level and complexity?",
        "user_guidance": "Next, choose a 1–5 rating for the organizational setting (1=small organization, 5=headquarters/agency level).",
        "field_type": "integer",
        "required": False,
        "category": "supervisory_factors",
        "examples": [
            3,
            "Probably a 3 — large organization but not headquarters",
            "Big, somewhat tangled org chart; we sit in the middle layers between the field and HQ",
        ],
        "sequence_weight": 110,
        "conditional": {"depends_on": "is_supervisor", "value": True},
    },
    
    "f3_supervisory_authorities": {
        "prompt": "Rate supervisory authorities factor (1-5): What supervisory authorities does this position exercise?",
        "user_guidance": "Then pick a 1–5 rating for supervisory authorities (1=limited, 5=full authority).",
        "field_type": "integer",
        "required": False,
        "category": "supervisory_factors",
        "examples": [
            4,
            "I’d select 4 — extensive authority over hiring, performance, and assignments",
            "They make most of the people decisions day‑to‑day, with only the big calls kicked up to higher management",
        ],
        "sequence_weight": 120,
        "conditional": {"depends_on": "is_supervisor", "value": True},
    },
    
    "f4_key_contacts": {
        "prompt": "Rate key contacts factor (1-5): What is the level and importance of contacts?",
        "user_guidance": "Now select a 1–5 rating for key contacts (1=mostly internal contacts, 5=executive or congressional-level contacts).",
        "field_type": "integer",
        "required": False,
        "category": "supervisory_factors",
        "examples": [
            3,
            "Regular external contacts with program partners and some senior officials (about a 3)",
            "Frequently talks with field leaders and occasionally with SES‑level stakeholders when projects are high‑visibility",
        ],
        "sequence_weight": 130,
        "conditional": {"depends_on": "is_supervisor", "value": True},
    },
    
    "f5_subordinate_details": {
        "prompt": "Describe the work performed by subordinates and its relationship to the organization's mission",
        "user_guidance": "Next, briefly describe what the subordinates do and how their work supports the organization’s mission.",
        "field_type": "text",
        "required": False,
        "category": "supervisory_details",
        "examples": [
            "Subordinates perform data analysis and reporting that supports performance metrics.",
            "The team cleans, analyzes, and visualizes program data, then turns it into dashboards and reports that leadership uses to make funding and policy decisions.",
            "They’re the people who make sense of messy spreadsheets and translate them into something leaders can actually act on.",
        ],
        "placeholder": "Describe subordinate work and how it supports the mission",
        "sequence_weight": 140,
        "conditional": {"depends_on": "is_supervisor", "value": True},
    },
    
    "f6_special_conditions": {
        "prompt": "Describe any special conditions affecting supervisory responsibilities (optional)",
        "user_guidance": "Finally, if there are any special conditions that affect supervision (like multiple locations or unusual authorities), describe them here—or leave blank if none.",
        "field_type": "text",
        "required": False,
        "category": "supervisory_details",
        "examples": [
            "Team is geographically dispersed across three regional offices.",
            "The team is spread across multiple time zones, with frequent remote collaboration and occasional travel to field sites.",
            "Everyone is scattered, working hybrid schedules with lots of after‑hours coordination to keep projects moving.",
        ],
        "placeholder": "Only if there are notable special conditions",
        "sequence_weight": 150,
        "conditional": {"depends_on": "is_supervisor", "value": True},
    }
}


# Sort by sequence_weight so iteration order is deterministic and logical
INTAKE_FIELDS: Dict[str, IntakeField] = {
    name: IntakeField(**config)
    for name, config in sorted(RAW_INTAKE_FIELDS.items(), key=lambda item: item[1].get("sequence_weight", 0))
}

# Base sequence (always ask first 8 core fields)
BASE_INTAKE_SEQUENCE = [
    "position_title",
    "series",
    "grade",
    "organization_hierarchy",
    "reports_to",
    "daily_activities",
    "major_duties",
    "is_supervisor",
]

# Full sequence includes optional supervisory factors (only if is_supervisor = True)
SUPERVISORY_ADDITIONAL = [
    "supervised_employees",
    "f1_program_scope",
    "f2_organizational_setting",
    "f3_supervisory_authorities",
    "f4_key_contacts",
    "f5_subordinate_details",
    "f6_special_conditions",
]

def get_intake_sequence(is_supervisor: bool | None) -> list:
    """Return ordered intake sequence based on supervisory status."""
    if is_supervisor:
        return BASE_INTAKE_SEQUENCE + SUPERVISORY_ADDITIONAL
    return BASE_INTAKE_SEQUENCE


# Common VA-relevant series with titles for interview guidance and validation.
# This list focuses on high-volume occupations across VHA, VBA, and NCA.
class VAJobSeriesEntry(BaseModel):
    """Pydantic model for a VA job series entry."""

    code: str = Field(..., description="4-digit job series code")
    title: str = Field(..., description="Official series title")


RAW_VA_JOB_SERIES: Dict[str, str] = {
    # Administration and program support
    "0301": "Miscellaneous Administration and Program",
    "0303": "Miscellaneous Clerk and Assistant",
    "0318": "Secretary",
    "0341": "Administrative Officer",
    "0342": "Administrative Officer (Trainee)",
    "0343": "Management and Program Analysis",
    "0346": "Logistics Management",
    "0360": "Equal Employment Opportunity",
    "0391": "Telecommunications",

    # Human resources and related
    "0201": "Human Resources Management",
    "0299": "Human Resources Management Student Trainee",

    # Business, finance, and contracting
    "0501": "Financial Administration and Program",
    "0525": "Accounting Technician",
    "0560": "Budget Analysis",
    "1102": "Contracting",

    # Health science and clinical support
    "0601": "General Health Science",
    "0602": "Physician",
    "0603": "Physician Assistant",
    "0610": "Nurse",
    "0620": "Practical Nurse",
    "0621": "Nursing Assistant",
    "0630": "Dietitian and Nutritionist",
    "0631": "Occupational Therapist",
    "0633": "Physical Therapist",
    "0640": "Health Aid and Technician",
    "0644": "Medical Technologist",
    "0647": "Diagnostic Radiologic Technologist",
    "0651": "Respiratory Therapist",
    "0660": "Pharmacist",
    "0661": "Pharmacy Technician",
    "0662": "Optometrist",
    "0665": "Speech Pathologist and Audiologist",
    "0670": "Health System Administrator",
    "0671": "Health System Specialist",
    "0672": "Prosthetic Representative",
    "0675": "Medical Records Administration",
    "0679": "Medical Support Assistance",
    "0685": "Public Health Program Specialist",
    "0688": "Sanitarian",

    # Social work, counseling, and psychology
    "0180": "Psychology",
    "0185": "Social Work",
    "0101": "Social Science",

    # Police, security, and emergency management
    "0083": "Police",
    "0085": "Security Guard",
    "0089": "Emergency Management",

    # Engineering, facilities, and environment
    "0801": "General Engineer",
    "0806": "Materials Engineering",
    "0810": "Civil Engineering",
    "0830": "Mechanical Engineering",
    "0850": "Electrical Engineering",
    "0854": "Computer Engineering",
    "0855": "Electronics Engineering",
    "0896": "Industrial Engineering Technician",
    "1170": "Realty",
    "1601": "Equipment, Facilities, and Services",
    "1640": "Facility Operations Services",

    # Information technology and data
    "1550": "Computer Science",
    "1560": "Data Science",
    "2210": "Information Technology Management",

    # Legal and compliance
    "0905": "Attorney",
    "0930": "Veterans Claims Examiner",
    "1801": "General Inspection, Investigation, Enforcement, and Compliance",

    # Education and vocational programs
    "1701": "General Education and Training",
    "1710": "Education and Vocational Training",
    "1720": "Education Program",
    "1740": "Education Services – Veterans",
}


VA_JOB_SERIES: Dict[str, VAJobSeriesEntry] = {
    code: VAJobSeriesEntry(code=code, title=title)
    for code, title in RAW_VA_JOB_SERIES.items()
}

