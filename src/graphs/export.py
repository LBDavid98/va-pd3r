"""Graph export utilities - Mermaid PNG with timestamp and styling."""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Union

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# Color scheme for the graph - organized by phase/function
STYLE_CONFIG = """
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#e8f4f8',
    'primaryTextColor': '#1a1a2e',
    'primaryBorderColor': '#4a90a4',
    'lineColor': '#5a7d8c',
    'secondaryColor': '#f0f7e6',
    'tertiaryColor': '#fff8e6'
  },
  'flowchart': {
    'curve': 'basis',
    'padding': 20,
    'nodeSpacing': 50,
    'rankSpacing': 60
  }
}}%%
"""

# Node style classes
STYLE_CLASSES = """
    %% Phase styles
    classDef startEnd fill:#e6f3ff,stroke:#2196F3,stroke-width:2px,color:#1565C0
    classDef init fill:#fff3e0,stroke:#FF9800,stroke-width:2px,color:#E65100
    classDef interview fill:#e8f5e9,stroke:#4CAF50,stroke-width:2px,color:#2E7D32
    classDef drafting fill:#f3e5f5,stroke:#9C27B0,stroke-width:2px,color:#6A1B9A
    classDef qa fill:#fff8e1,stroke:#FFC107,stroke-width:2px,color:#F57F17
    classDef routing fill:#fce4ec,stroke:#E91E63,stroke-width:1px,color:#880E4F,stroke-dasharray:3
"""

# Map nodes to their style classes
NODE_STYLES = {
    # Start/End
    "__start__": "startEnd",
    "__end__": "startEnd",
    "end_conversation": "startEnd",
    # Init phase
    "init": "init",
    # Interview phase  
    "user_input": "interview",
    "classify_intent": "routing",
    "map_answers": "interview",
    "answer_question": "interview",
    "prepare_next": "interview",
    "check_interview_complete": "interview",
    # Requirements/FES phase
    "evaluate_fes": "drafting",
    "gather_requirements": "drafting",
    # Drafting phase
    "generate_element": "drafting",
    "qa_review": "qa",
    "handle_draft_response": "drafting",
    "advance_element": "routing",
}

# Node display names (more readable)
NODE_DISPLAY_NAMES = {
    "__start__": "Start",
    "__end__": "End",
    "init": "Initialize<br>Session",
    "user_input": "Get User<br>Input",
    "classify_intent": "Classify<br>Intent",
    "map_answers": "Map<br>Answers",
    "answer_question": "Answer<br>Question",
    "prepare_next": "Prepare<br>Next Question",
    "check_interview_complete": "Check Interview<br>Complete",
    "end_conversation": "End<br>Conversation",
    "evaluate_fes": "Evaluate<br>FES Factors",
    "gather_requirements": "Gather Draft<br>Requirements",
    "generate_element": "Generate<br>Draft Element",
    "qa_review": "QA<br>Review",
    "handle_draft_response": "Handle Draft<br>Response",
    "advance_element": "Advance to<br>Next Element",
}


def get_styled_mermaid_syntax(graph) -> str:
    """
    Convert LangGraph to styled Mermaid syntax with colors and formatting.
    
    Args:
        graph: Compiled LangGraph
        
    Returns:
        Styled Mermaid diagram string
    """
    # Get raw mermaid from LangGraph
    raw_mermaid = ""
    if hasattr(graph, "get_graph"):
        g = graph.get_graph()
        if hasattr(g, "draw_mermaid"):
            raw_mermaid = g.draw_mermaid()
    
    if not raw_mermaid:
        return _get_fallback_mermaid()
    
    # Parse and restyle the mermaid
    lines = raw_mermaid.split("\n")
    styled_lines = [STYLE_CONFIG.strip(), "graph TD"]
    
    # Track which nodes we've seen
    seen_nodes = set()
    edges = []
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith("---") or line.startswith("config:") or line.startswith("flowchart:"):
            continue
        if line.startswith("curve:") or line.startswith("graph "):
            continue
        if line.startswith("classDef"):
            continue  # We'll add our own
        
        # Node definitions - check for various mermaid node shapes: (), [], {}, ([])
        is_node = False
        node_name = None
        if "--" not in line and "-." not in line:
            # Try to extract node name from various bracket types
            for bracket in ["(", "[", "{"]:
                if bracket in line:
                    node_name = line.split(bracket)[0].strip().rstrip(";")
                    if node_name:
                        is_node = True
                        break
        
        if is_node and node_name and node_name not in seen_nodes:
            seen_nodes.add(node_name)
            styled_lines.append(_format_node(node_name))
        
        # Edge definitions
        elif "-->" in line or "-.->" in line or "-.>" in line or "-." in line:
            # Replace any \n with <br> in edge labels
            edge = line.rstrip(";").replace("\\n", "<br>")
            edges.append(edge)
    
    # Add blank line before edges
    styled_lines.append("")
    styled_lines.append("    %% Edges")
    
    # Add edges with proper formatting
    for edge in edges:
        styled_lines.append(f"    {edge}")
    
    # Add style classes
    styled_lines.append("")
    styled_lines.append("    %% Styles")
    styled_lines.append(STYLE_CLASSES.strip())
    
    # Apply styles to nodes
    styled_lines.append("")
    for node_name in seen_nodes:
        if node_name in NODE_STYLES:
            styled_lines.append(f"    class {node_name} {NODE_STYLES[node_name]}")
    
    return "\n".join(styled_lines)


def _format_node(node_name: str) -> str:
    """Format a node with display name and proper shape."""
    display_name = NODE_DISPLAY_NAMES.get(node_name, node_name.replace("_", " ").title())
    
    # Use different shapes for different node types
    if node_name in ("__start__", "__end__"):
        return f"    {node_name}(({display_name}))"  # Circle
    elif node_name in ("classify_intent", "advance_element"):
        return f"    {node_name}{{{display_name}}}"  # Diamond/rhombus
    elif node_name == "end_conversation":
        return f"    {node_name}([{display_name}])"  # Stadium shape
    else:
        return f"    {node_name}[{display_name}]"  # Rectangle


def _get_fallback_mermaid() -> str:
    """Fallback mermaid diagram if graph export fails."""
    return """graph TD
    __start__((Start))
    init[Initialize Session]
    user_input[Get User Input]
    classify_intent{Classify Intent}
    end_conversation([End Conversation])
    __end__((End))
    
    __start__ --> init
    init --> user_input
    user_input --> classify_intent
    classify_intent --> end_conversation
    end_conversation --> __end__
"""


def get_mermaid_syntax(graph) -> str:
    """
    Convert LangGraph to Mermaid syntax.
    
    This is an alias for get_styled_mermaid_syntax for backwards compatibility.
    """
    return get_styled_mermaid_syntax(graph)


def add_timestamp_overlay(image_path: Path) -> None:
    """Add timestamp to top-right corner of image."""
    if not HAS_PIL:
        return

    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Try to use a basic font, fall back to default
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Calculate position (top-right with padding)
    bbox = draw.textbbox((0, 0), timestamp, font=font)
    text_width = bbox[2] - bbox[0]
    x = img.width - text_width - 10
    y = 10

    # Draw background rectangle
    padding = 4
    draw.rectangle(
        [x - padding, y - padding, x + text_width + padding, y + (bbox[3] - bbox[1]) + padding],
        fill="white",
        outline="gray"
    )

    # Draw timestamp
    draw.text((x, y), timestamp, fill="black", font=font)

    img.save(image_path)


def export_graph_png(graph, output_path: Union[str, Path]) -> bool:
    """
    Export graph to PNG with timestamp and save Mermaid source.

    Always saves the .mmd file alongside the PNG for reference.
    
    Args:
        graph: Compiled LangGraph
        output_path: Path for PNG output (will also create .mmd alongside)
        
    Returns:
        True if PNG was generated successfully, False if only .mmd was created.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mermaid_code = get_styled_mermaid_syntax(graph)
    
    # Always save the mermaid source file
    mmd_path = output_path.with_suffix(".mmd")
    mmd_path.write_text(mermaid_code)

    # Try mermaid-cli for PNG generation
    png_generated = False
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as f:
            f.write(mermaid_code)
            temp_mmd_path = f.name

        result = subprocess.run(
            [
                "npx", "-y", "@mermaid-js/mermaid-cli",
                "-i", temp_mmd_path,
                "-o", str(output_path),
                "-b", "white",
                "-s", "2",      # Scale factor for higher resolution
                "-q",           # Quiet mode
            ],
            capture_output=True,
            text=True,
            timeout=60  # Increased timeout for npx download
        )

        Path(temp_mmd_path).unlink(missing_ok=True)

        if result.returncode == 0 and output_path.exists():
            add_timestamp_overlay(output_path)
            png_generated = True
            print(f"✓ Graph exported to {output_path}")
        else:
            if result.stderr:
                print(f"Mermaid CLI warning: {result.stderr[:200]}")

    except subprocess.TimeoutExpired:
        print("Mermaid CLI timed out - PNG not generated")
    except FileNotFoundError:
        print("npx not found - PNG not generated (install Node.js)")
    except subprocess.SubprocessError as e:
        print(f"Mermaid CLI error: {e}")

    # Report what we created
    print(f"✓ Mermaid source saved to {mmd_path}")
    
    if not png_generated:
        print("  Tip: View .mmd in VS Code with Mermaid preview extension")
    
    return png_generated


def export_graph(
    graph,
    output_dir: Union[str, Path] = "output/graphs",
    base_name: str = "main_graph"
) -> tuple[Path, Path | None]:
    """
    Export graph to both Mermaid (.mmd) and PNG formats.
    
    This is the recommended export function that always produces
    a .mmd file and attempts to create a .png.
    
    Args:
        graph: Compiled LangGraph
        output_dir: Directory for output files
        base_name: Base filename without extension
        
    Returns:
        Tuple of (mmd_path, png_path or None)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    mmd_path = output_dir / f"{base_name}.mmd"
    png_path = output_dir / f"{base_name}.png"
    
    mermaid_code = get_styled_mermaid_syntax(graph)
    mmd_path.write_text(mermaid_code)
    
    png_success = export_graph_png(graph, png_path)
    
    return (mmd_path, png_path if png_success else None)
