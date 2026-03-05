# LangGraph Agent Toolkit 🛠️

> The Rolls-Royce of agent performance tuning tools for LangGraph projects.

A comprehensive, portable toolkit for analyzing, testing, and tuning LangGraph agents. Import into any LangGraph project for deep performance insights and automated testing.

---

## 🚀 Quick Start

```bash
# From your LangGraph project root
pip install -e agent_toolkit/  # or copy the folder

# Analyze a specific node
anode init_node -n 5

# Full graph analysis
anode full -n 3

# Run automated test scripts
agentscript scripts/test_flow.txt --stream

# Health check
agent_health

# Lint for anti-patterns
agent_lint
```

---

## 📦 Installation

### Option 1: Copy to Your Project

Copy the `agent_toolkit/` folder to your LangGraph project root.

### Option 2: Install as Package

```bash
cd agent_toolkit
pip install -e .
```

### Option 3: Add to Your Project's Dependencies

Add to `pyproject.toml`:
```toml
[tool.poetry.scripts]
anode = "agent_toolkit.tools.anode:main"
agentscript = "agent_toolkit.tools.agentscript:main"
agent_health = "agent_toolkit.tools.health_check:main"
agent_lint = "agent_toolkit.tools.lint:main"
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_PROJECT_ROOT` | Current directory | Project root path |
| `AGENT_TRACE_DIR` | `output/logs` | Trace log directory |
| `AGENT_NODES_DIR` | `src/nodes` | Nodes source directory |
| `AGENT_PROMPTS_DIR` | `src/prompts` | Prompts directory |
| `AGENT_GRAPH_MODULE` | `src.graphs.main_graph` | Graph module path |
| `AGENT_ANALYSIS_MODEL` | `gpt-5.2` | Model for analysis (OpenAI GPT-5.2) |
| `AGENT_ANALYSIS_TEMP` | `0.1` | Temperature for analysis |
| `OPENAI_API_KEY` | Required | OpenAI API key |

### Config File

Create `agent_toolkit_config.json`:
```json
{
  "project_root": "/path/to/project",
  "trace_dir": "output/logs",
  "nodes_dir": "src/nodes",
  "prompts_dir": "src/prompts",
  "graph_module": "src.graphs.main_graph",
  "analysis_model": "gpt-5.2",
  "analysis_temperature": 0.1
}
```

Use with: `anode --config agent_toolkit_config.json init_node`

---

## 🔍 anode - Node Analyzer

Deep analysis of individual node behavior using LLM-powered insights.

### Usage

```bash
# Analyze a specific node from last N runs
anode <node_name> -n <N>

# Full graph analysis
anode full -n <N>

# List available nodes
anode --list

# Show cost breakdown
anode --costs

# Save analysis to file
anode init_node -n 5 -o analysis_report.md
```

### What It Analyzes

For **single nodes**:
- 📥 **Input Quality**: Are the right state fields being passed?
- 📝 **Prompt Analysis**: Is the prompt well-structured and efficient?
- 🎯 **State Utilization**: Are we using all available information?
- ⚙️ **Model Configuration**: Right model? Temperature setting?
- 💰 **Cost Efficiency**: Token usage and cost optimization
- 🔄 **Output Quality**: Response consistency and accuracy

For **full graph** (`anode full`):
- 🏗️ **Architecture Review**: Graph structure appropriateness
- 📊 **State Management**: Efficient state flow analysis
- 🔀 **Conversation Flow**: User experience coherence
- ⚡ **Performance Analysis**: Bottlenecks and cost centers
- ✅ **Best Practices Check**: LangGraph pattern compliance
- 🚫 **Anti-Pattern Detection**: Common issues identification

### Example Output

```
══════════════════════════════════════════════════════════════
  ANODE - LangGraph Node Analyzer
══════════════════════════════════════════════════════════════

## 1. Executive Summary
The init_node is performing well with 100% success rate, but 
there's opportunity to reduce token usage by ~30% through 
prompt optimization.

## 2. Input Analysis
✓ State fields properly accessed: messages, phase, interview_data
⚠ Unused field 'context_window' could enhance responses

## 3. Prompt Analysis
- Structure: Well-organized with clear sections
- Efficiency: ~1,200 tokens could be reduced to ~800
- Clarity: Good, but system instructions could be more specific

## 4. Model Configuration Review
- Current: gpt-5.2 (temperature: 0.3)
- Analysis: GPT-5.2 is the recommended model for complex agentic tasks

## 5. Recommendations (prioritized)
1. [HIGH] Reduce system prompt length by removing redundant instructions
2. [MEDIUM] Evaluate token usage for cost optimization
3. [LOW] Add structured output for more consistent parsing
```

---

## 🎬 agentscript - Automated Conversation Runner

Run scripted conversations for testing, benchmarking, and trace generation.

### Usage

```bash
# Run a script
agentscript <script_file>

# Stream responses in real-time
agentscript <script_file> --stream

# Adjust verbosity (0-3)
agentscript <script_file> -v 2

# Create a new script template
agentscript --create my_test

# List available scripts
agentscript --list
```

### Script Format

```text
# Comment line - ignored
This is a user message sent to the agent

# Special commands:
@PAUSE              # Wait for Enter key
@WAIT:2.5           # Wait 2.5 seconds
@EXPECT:hello       # Assert response contains "hello"
@END                # End conversation

# Example script
Hello, I'd like to test the agent.
@EXPECT:welcome
What can you help me with?
@PAUSE
Thanks, goodbye!
@END
```

### Verbosity Levels

- `0` - Quiet: Only errors and final status
- `1` - Normal: User messages and agent responses
- `2` - Verbose: + Token counts, costs, timing
- `3` - Debug: + Full execution details

### Beautiful Terminal Output

```
╔══════════════════════════════════════════════════════════════╗
║  🤖 AGENTSCRIPT - Automated Conversation Runner              ║
╠══════════════════════════════════════════════════════════════╣
║  Script: test_interview.txt                                  ║
║  Commands: 12                                                ║
║  Started: 2026-01-14 10:30:00                                ║
╚══════════════════════════════════════════════════════════════╝

───────────────────────────────────────────────────────────────
👤 USER [1]
Hello, I'd like to create a new position description.

🤖 AGENT
Welcome! I'd be happy to help you create a position description.
Let's start with some basic information...

✓ Expected text found: 'position description...'
───────────────────────────────────────────────────────────────

═══════════════════════════════════════════════════════════════
Script COMPLETED
  Messages: 6
  Duration: 45.2s
  Tokens:   12,450
  Cost:     $0.0234
```

---

## 🏥 agent_health - Health Diagnostics

Comprehensive health checks for your LangGraph project.

### Usage

```bash
# Run all health checks
agent_health

# Output as JSON
agent_health --json

# Specify project root
agent_health --project-root /path/to/project
```

### Checks Performed

| Check | Description |
|-------|-------------|
| Project Structure | Essential files present (pyproject.toml, README.md) |
| Directory Structure | Required directories exist |
| Environment Variables | API keys and configuration set |
| Graph Module | Graph can be imported and compiled |
| Nodes Directory | Node files present and valid |
| Prompts Directory | Prompt templates available |
| Trace Directory | Traces available for analysis |
| Dependencies | Required packages installed |
| Configuration | Settings are valid |

### Example Output

```
════════════════════════════════════════════════════════════════
AGENT HEALTH CHECK REPORT
════════════════════════════════════════════════════════════════
Project: pd3r

Status: ✅ HEALTHY

────────────────────────────────────────────────────────────────

✅ Project Structure
   All essential files present

✅ Directory Structure
   All essential directories present

✅ Environment Variables
   All required variables set
     • optional_present: ['LANGCHAIN_API_KEY', 'LOCAL_TRACING']

✅ Graph Module
   Graph module loads correctly
     • module: src.graphs.main_graph

✅ Nodes Directory
   Found 18 Python files, 15 node files
     • total_files: 18
     • node_files: 15

✅ Trace Directory
   Found 23 trace files
     • newest: 20260114_103045_abc123.jsonl
     • newest_time: 2026-01-14 10:30

✅ Dependencies
   All required dependencies installed
     • versions: {'langgraph': '1.0.6', 'langchain_openai': '1.1.7'}

✅ Configuration
   Configuration looks valid

════════════════════════════════════════════════════════════════
```

---

## 🔬 agent_lint - Static Analysis

Detect anti-patterns and common issues in LangGraph implementations.

### Usage

```bash
# Lint entire project
agent_lint

# Lint specific file or directory
agent_lint src/nodes/

# Show suggestions
agent_lint -v

# Output as JSON
agent_lint --json

# List available rules
agent_lint --rules
```

### Lint Rules

| Rule | Severity | Description |
|------|----------|-------------|
| `LG001` | Warning | Inline prompts should be moved to templates |
| `LG002` | Error | Manual orchestration - use graph edges |
| `LG003` | Warning | Node functions should have error handling |
| `LG004` | Info | State may be accumulating unnecessary data |
| `LG005` | Info | Functions should have type hints |
| `LG006` | Warning | Model names should be configurable |
| `LG007` | Info | State field may be set but never used |

### Example Output

```
════════════════════════════════════════════════════════════════
AGENT LINT REPORT
════════════════════════════════════════════════════════════════
Files scanned: 18
Issues found: 5
  🔴 Errors: 0
  🟡 Warnings: 3
  ℹ️  Info: 2

────────────────────────────────────────────────────────────────
📄 src/nodes/generate_element_node.py

  🟡 Line 45: [LG001] Long inline string looks like a prompt
     💡 Move to prompts directory for better maintainability

  🟡 Line 89: [LG006] Hardcoded model name detected
     💡 Use environment variable or config for model selection

────────────────────────────────────────────────────────────────
📄 src/nodes/qa_review_node.py

  ℹ️ Line 1: [LG007] State fields may be unused: draft_history
     💡 Verify these fields are used in other nodes

════════════════════════════════════════════════════════════════
```

---

## 🔌 Integration with Your Project

### Add to AGENTS.MD

```markdown
## Agent Toolkit Commands

- `anode <node> -n 5` - Analyze node performance
- `anode full` - Full graph analysis
- `agentscript scripts/<name>.txt` - Run test script
- `agent_health` - Health diagnostics
- `agent_lint` - Check for anti-patterns

### Generating Traces

Enable tracing to generate data for analysis:
```bash
LOCAL_TRACING=true poetry run python -m src.main
```
```

### Programmatic Usage

```python
from agent_toolkit import TraceAnalyzer, NodeAnalyzer, analyze_node

# Analyze traces
analyzer = TraceAnalyzer("output/logs")
runs = analyzer.load_recent_runs(5)
print(analyzer.format_cost_report())

# Analyze a specific node
report = analyze_node("init_node", n_runs=5, verbose=True)
print(report)

# Run health check
from agent_toolkit import run_health_check
report = run_health_check()
if not report.passed:
    print("Issues found!")

# Lint the project
from agent_toolkit import lint_graph
report = lint_graph()
for issue in report.issues:
    print(f"{issue.file}:{issue.line} - {issue.message}")
```

---

## 📁 Directory Structure

```
agent_toolkit/
├── __init__.py              # Main exports
├── README.md                # This file
├── core/
│   ├── __init__.py
│   ├── config.py            # Configuration management
│   ├── trace_analyzer.py    # Trace loading and analysis
│   └── node_analyzer.py     # Node source and behavior analysis
├── prompts/
│   └── __init__.py          # LLM analysis prompts
├── tools/
│   ├── __init__.py
│   ├── anode.py             # Node analyzer CLI
│   ├── agentscript.py       # Script runner CLI
│   ├── health_check.py      # Health diagnostics CLI
│   └── lint.py              # Static analysis CLI
└── scripts/
    ├── test_interview.txt   # Sample test script
    ├── test_edge_cases.txt  # Edge case tests
    └── test_long_conversation.txt
```

---

## 🔮 Advanced Features

### Custom Analysis Prompts

Override the default analysis prompts:

```python
from agent_toolkit.prompts import NODE_ANALYSIS_SYSTEM, NODE_ANALYSIS_USER

# Customize for your domain
MY_SYSTEM = NODE_ANALYSIS_SYSTEM + """
\nAdditional context: This is a federal HR application.
Focus on OPM compliance in your analysis.
"""
```

### Custom Lint Rules

Add your own lint rules:

```python
from agent_toolkit.tools.lint import LintRule, LintIssue

class MyCustomRule(LintRule):
    rule_id = "CUSTOM001"
    severity = "warning"
    description = "My custom check"
    
    def check_file(self, file_path, content, tree):
        issues = []
        # Your logic here
        return issues

# Add to linter
from agent_toolkit.tools.lint import AgentLinter
linter = AgentLinter()
linter.rules.append(MyCustomRule())
```

### Trace Format

The toolkit expects traces in JSONL format with this structure:

```jsonl
{"event": "run_summary", "run_id": "abc123", "total_cost": 0.05, ...}
{"event": "node_execution", "node_name": "init", "state_on_entry": {...}, "llm_calls": [...]}
{"event": "node_execution", "node_name": "classify_intent", ...}
```

---

## 🤝 Contributing

Found a bug or want to add a feature? The toolkit is designed to be extensible:

1. **New lint rules**: Add to `tools/lint.py`
2. **New health checks**: Add to `tools/health_check.py`  
3. **Analysis prompts**: Modify `prompts/__init__.py`
4. **Script commands**: Extend `tools/agentscript.py`

---

## 📄 License

MIT License - Use freely in your LangGraph projects!

---

## 🙏 Acknowledgments

Built for the LangGraph community. Inspired by the need for better agent observability and testing tools.

Special thanks to:
- The LangChain/LangGraph team for the excellent framework
- Everyone building AI agents who needs better tooling

---

*Made with ❤️ for agent developers who care about quality*
