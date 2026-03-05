"""Capture graph state snapshots at each phase boundary for test scripts.

Runs the Program Analyst and Supervisory scripts end-to-end through the graph,
capturing serializable state at each phase transition. Saves fixtures that the
frontend Testing tab can use to seed sessions at any starting point.

Usage:
    poetry run python scripts/capture_test_states.py
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.graphs.main_graph import build_graph
from src.models.interview import InterviewData

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("capture_states")

# Suppress noisy loggers
for name in ["httpx", "openai", "httpcore"]:
    logging.getLogger(name).setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Script definitions (mirrors frontend autoFillScript.ts)
# ---------------------------------------------------------------------------

SCRIPTS = {
    "program-analyst": {
        "name": "GS-11 Program Analyst",
        "opening": "Hi, I'd like to create a position description for a Program Analyst.",
        "fields": {
            "position_title": "Program Analyst",
            "series": "0343",
            "grade": "11",
            "organization_hierarchy": "Department of Veterans Affairs, Veterans Health Administration, Office of Health Informatics",
            "reports_to": "Supervisory Program Analyst",
            "daily_activities": "Analyze program performance data and prepare reports; Coordinate with stakeholders on program requirements; Develop and maintain tracking systems for key performance indicators; Draft policy recommendations based on data analysis; Support budget formulation and execution reviews",
            "major_duties": "Analyze healthcare program effectiveness and develop improvement recommendations 40%; Coordinate cross-functional projects and track milestones 30%; Prepare briefings, reports, and policy documents for senior leadership 30%",
            "is_supervisor": "no",
            "mission_text": "Deliver modern, innovative, and user-centered digital health solutions to create outstanding health care experiences for Veterans and their care teams.",
            "work_schedule": "Full-time permanent",
            "supervisor_name": "Sarah Chen, Branch Chief",
        },
        "phase_responses": {
            "requirements": "yes, that looks correct",
            "review": "approved",
            "complete": "no",
        },
        "drafting_response": "approve",
    },
    "supervisory": {
        "name": "GS-14 Supervisory IT Specialist",
        "opening": "I need to write a PD for a supervisory IT Specialist position.",
        "fields": {
            "position_title": "Supervisory IT Specialist (SYSADMIN)",
            "series": "2210",
            "grade": "14",
            "organization_hierarchy": "Department of Veterans Affairs, Office of Information and Technology, Enterprise Cloud Solutions Office",
            "reports_to": "Deputy Chief Information Officer",
            "daily_activities": "Oversee cloud infrastructure operations and team of system administrators; Conduct performance reviews and mentoring sessions; Coordinate with security team on ATO compliance; Review and approve change requests; Attend leadership meetings on IT modernization",
            "major_duties": "Direct cloud infrastructure operations and ensure 99.9% uptime for Veteran-facing systems 35%; Supervise and develop a team of 8 IT specialists across GS-9 to GS-13 levels 30%; Lead IT modernization initiatives and cloud migration projects 20%; Serve as technical advisor to senior leadership on infrastructure strategy 15%",
            "is_supervisor": "yes",
            "supervised_employees": "3 GS-13 Senior System Administrators, 3 GS-12 System Administrators, 2 GS-9 Junior System Administrators",
            "num_supervised": "8",
            "percent_supervising": "30",
            "f1_program_scope": "4",
            "f2_organizational_setting": "3",
            "f3_supervisory_authorities": "4",
            "f4_key_contacts": "3",
            "f5_subordinate_details": "8 subordinates across 3 grade levels performing systems administration, cloud operations, and security compliance work",
            "f6_special_conditions": "24/7 on-call responsibility for critical system outages; manages classified and sensitive Veteran health data systems",
            "mission_text": "Provide reliable, secure, and modern IT infrastructure that enables VA to deliver world-class healthcare and benefits services to our nation's Veterans.",
            "work_schedule": "Full-time permanent",
            "supervisor_name": "Robert Kim, Deputy CIO",
        },
        "phase_responses": {
            "requirements": "yes, confirmed",
            "review": "approved",
            "complete": "no",
        },
        "drafting_response": "approve",
    },
}


def _serialize_state(state_values: dict) -> dict:
    """Extract serializable state for fixture storage."""
    # Convert messages to simple dicts
    messages = []
    for msg in state_values.get("messages", []):
        messages.append({
            "type": msg.__class__.__name__,
            "content": msg.content[:200] if hasattr(msg, "content") else str(msg)[:200],
        })

    # Extract interview data values
    interview_data = state_values.get("interview_data", {})
    interview_values = {}
    is_supervisor = None
    if isinstance(interview_data, InterviewData):
        for field_name in interview_data.model_fields:
            element = getattr(interview_data, field_name, None)
            if element and hasattr(element, "value") and element.value is not None:
                interview_values[field_name] = element.value
                if field_name == "is_supervisor":
                    is_supervisor = bool(element.value)
    elif isinstance(interview_data, dict):
        for field_name, element in interview_data.items():
            if isinstance(element, dict) and element.get("value") is not None:
                interview_values[field_name] = element["value"]
                if field_name == "is_supervisor":
                    is_supervisor = bool(element["value"])

    # Extract draft elements
    draft_elements = []
    for elem_dict in state_values.get("draft_elements", []):
        if isinstance(elem_dict, dict):
            draft_elements.append({
                "name": elem_dict.get("name"),
                "display_name": elem_dict.get("display_name"),
                "status": elem_dict.get("status"),
                "content": elem_dict.get("content", "")[:100] + "..." if elem_dict.get("content") else None,
            })

    return {
        "phase": state_values.get("phase", "init"),
        "message_count": len(messages),
        "last_message": messages[-1]["content"] if messages else None,
        "interview_values": interview_values,
        "is_supervisor": is_supervisor,
        "missing_fields": state_values.get("missing_fields", []),
        "current_field": state_values.get("current_field"),
        "current_element_name": state_values.get("current_element_name"),
        "draft_element_count": len(draft_elements),
        "draft_elements": draft_elements,
        "should_end": state_values.get("should_end", False),
    }


async def _get_response(script: dict, state_values: dict) -> str:
    """Determine what to say next based on current state."""
    phase = state_values.get("phase", "init")

    if phase == "interview":
        # Use current_field from state (matches what prepare_next_node asked about)
        current_field = state_values.get("current_field")
        if current_field:
            answer = script["fields"].get(current_field)
            if answer:
                return answer
        # Fallback to missing_fields[0]
        missing = state_values.get("missing_fields", [])
        if missing:
            field = missing[0]
            answer = script["fields"].get(field)
            if answer:
                return answer
            return f"Test data for {field.replace('_', ' ')}"
        return "yes, that's everything"

    if phase in script["phase_responses"]:
        return script["phase_responses"][phase]

    if phase == "drafting":
        return script["drafting_response"]

    return "continue"


async def run_script(script_id: str, script: dict) -> dict[str, dict]:
    """Run a script through the graph and capture state at each phase."""
    logger.info(f"\n{'='*60}\nRunning script: {script['name']}\n{'='*60}")

    checkpointer = MemorySaver()
    builder = build_graph()
    graph = builder.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": f"capture-{script_id}"}}

    snapshots: dict[str, dict] = {}
    seen_phases: set[str] = set()
    turn = 0
    max_turns = 60  # Safety limit
    stuck_count = 0  # Detect dead ends
    last_missing = -1

    # Initial run
    result = None
    async for event in graph.astream({}, config, stream_mode="values"):
        result = event

    if result:
        phase = result.get("phase", "init")
        snap = _serialize_state(result)
        snapshots[f"init"] = snap
        seen_phases.add("init")
        logger.info(f"  Turn 0: phase={phase}, msg_count={snap['message_count']}")

    # Send opening message
    user_msg = script["opening"]

    while turn < max_turns:
        turn += 1
        logger.info(f"  Turn {turn}: sending '{user_msg[:60]}...' " if len(user_msg) > 60 else f"  Turn {turn}: sending '{user_msg}'")

        result = None
        for attempt in range(3):
            try:
                async for event in graph.astream(
                    Command(resume=user_msg), config, stream_mode="values"
                ):
                    result = event
                break  # Success
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"    Retry {attempt+1}/2 after error: {e}")
                    await asyncio.sleep(2)
                else:
                    raise

        if not result:
            logger.warning("  No result from graph!")
            break

        phase = result.get("phase", "unknown")
        snap = _serialize_state(result)
        logger.info(f"    → phase={phase}, missing={len(snap['missing_fields'])}, elements={snap['draft_element_count']}")

        # Capture snapshot at each new phase
        if phase not in seen_phases:
            snapshots[phase] = snap
            seen_phases.add(phase)
            logger.info(f"    ★ Captured snapshot for phase: {phase}")

        # Stuck detection: if missing_fields count hasn't changed in 5 turns, bail
        current_missing = len(snap["missing_fields"])
        if current_missing == last_missing and current_missing > 0:
            stuck_count += 1
            if stuck_count >= 5:
                logger.error(f"  STUCK: missing_fields={current_missing} unchanged for {stuck_count} turns, aborting")
                break
        else:
            stuck_count = 0
            last_missing = current_missing

        # Check if done
        if result.get("should_end", False):
            logger.info("  Session ended (should_end=True)")
            break

        if phase == "complete" and "complete" in seen_phases:
            logger.info("  Reached complete phase, stopping")
            break

        # Determine next response
        user_msg = await _get_response(script, result)

        if user_msg == "no" and phase == "complete":
            # Send the "no" and capture final state
            result = None
            async for event in graph.astream(
                Command(resume=user_msg), config, stream_mode="values"
            ):
                result = event
            if result:
                snapshots["complete"] = _serialize_state(result)
            break

    logger.info(f"\n  Captured {len(snapshots)} phase snapshots: {list(snapshots.keys())}")
    return snapshots


async def main():
    output_dir = Path("output/test_fixtures")
    output_dir.mkdir(parents=True, exist_ok=True)

    all_snapshots = {}

    for script_id, script in SCRIPTS.items():
        try:
            snapshots = await run_script(script_id, script)
            all_snapshots[script_id] = snapshots

            # Save individual script fixture
            fixture_path = output_dir / f"{script_id}_states.json"
            with open(fixture_path, "w") as f:
                json.dump(snapshots, f, indent=2, default=str)
            logger.info(f"Saved fixture: {fixture_path}")

        except Exception as e:
            logger.error(f"Script {script_id} failed: {e}", exc_info=True)

    # Save combined fixture
    combined_path = output_dir / "all_states.json"
    with open(combined_path, "w") as f:
        json.dump(all_snapshots, f, indent=2, default=str)
    logger.info(f"\nSaved combined fixture: {combined_path}")

    # Summary
    print("\n" + "=" * 60)
    print("CAPTURE SUMMARY")
    print("=" * 60)
    for script_id, snapshots in all_snapshots.items():
        print(f"\n{SCRIPTS[script_id]['name']}:")
        for phase, snap in snapshots.items():
            fields = len(snap.get("interview_values", {}))
            elements = snap.get("draft_element_count", 0)
            print(f"  {phase:15s}  fields={fields:2d}  elements={elements:2d}  msgs={snap['message_count']}")


if __name__ == "__main__":
    asyncio.run(main())
