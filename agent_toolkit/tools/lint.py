#!/usr/bin/env python3
"""agent_lint - Static analysis tool for LangGraph agents.

Detects common anti-patterns and issues in LangGraph implementations.

Anti-patterns detected:
- Manual orchestration instead of graph edges
- Inline prompts instead of using prompt templates
- Missing error handling
- State pollution
- Inefficient LLM usage patterns
- Missing type hints
- Inconsistent naming conventions
"""

import argparse
import ast
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add parent to path for imports when run directly
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_toolkit.core.config import ToolkitConfig, get_config, set_config


@dataclass
class LintIssue:
    """A single lint issue."""
    
    file: str
    line: int
    column: int
    rule: str
    severity: str  # error, warning, info
    message: str
    suggestion: str | None = None


@dataclass
class LintReport:
    """Complete lint report."""
    
    issues: list[LintIssue]
    files_scanned: int
    
    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")
    
    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")
    
    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "info")
    
    def format_report(self, verbose: bool = False) -> str:
        """Format report for display."""
        lines = [
            "=" * 60,
            "AGENT LINT REPORT",
            "=" * 60,
            f"Files scanned: {self.files_scanned}",
            f"Issues found: {len(self.issues)}",
            f"  🔴 Errors: {self.error_count}",
            f"  🟡 Warnings: {self.warning_count}",
            f"  ℹ️  Info: {self.info_count}",
            "",
        ]
        
        if not self.issues:
            lines.append("✅ No issues found!")
        else:
            # Group by file
            by_file: dict[str, list[LintIssue]] = {}
            for issue in self.issues:
                if issue.file not in by_file:
                    by_file[issue.file] = []
                by_file[issue.file].append(issue)
            
            for file, issues in sorted(by_file.items()):
                lines.append("-" * 60)
                lines.append(f"📄 {file}")
                lines.append("")
                
                for issue in sorted(issues, key=lambda x: x.line):
                    icon = {
                        "error": "🔴",
                        "warning": "🟡",
                        "info": "ℹ️",
                    }.get(issue.severity, "❓")
                    
                    lines.append(f"  {icon} Line {issue.line}: [{issue.rule}] {issue.message}")
                    
                    if verbose and issue.suggestion:
                        lines.append(f"     💡 {issue.suggestion}")
                
                lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)


# =============================================================================
# Lint Rules
# =============================================================================

class LintRule:
    """Base class for lint rules."""
    
    rule_id: str
    severity: str
    description: str
    
    def check_file(self, file_path: Path, content: str, tree: ast.AST) -> list[LintIssue]:
        """Check a file for issues.
        
        Args:
            file_path: Path to the file
            content: File content as string
            tree: Parsed AST
            
        Returns:
            List of issues found
        """
        raise NotImplementedError


class InlinePromptRule(LintRule):
    """Detect inline prompts that should be in templates."""
    
    rule_id = "LG001"
    severity = "warning"
    description = "Inline prompts should be moved to prompt templates"
    
    def check_file(self, file_path: Path, content: str, tree: ast.AST) -> list[LintIssue]:
        issues = []
        
        # Look for long string literals that look like prompts
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                # Heuristics for detecting prompts
                if len(value) > 200 and any(kw in value.lower() for kw in [
                    "you are", "system:", "assistant:", "respond",
                    "analyze", "generate", "provide", "instruction",
                ]):
                    issues.append(LintIssue(
                        file=str(file_path),
                        line=node.lineno,
                        column=node.col_offset,
                        rule=self.rule_id,
                        severity=self.severity,
                        message="Long inline string looks like a prompt",
                        suggestion="Move to prompts directory for better maintainability",
                    ))
        
        return issues


class ManualOrchestrationRule(LintRule):
    """Detect manual orchestration instead of using graph edges."""
    
    rule_id = "LG002"
    severity = "error"
    description = "Manual orchestration detected - use graph edges instead"
    
    def check_file(self, file_path: Path, content: str, tree: ast.AST) -> list[LintIssue]:
        issues = []
        
        # Look for patterns that suggest manual orchestration
        patterns = [
            (r'if.*next.*node|if.*node.*==', "Conditional node dispatch"),
            (r'while.*state|for.*node.*in', "Loop-based node execution"),
            (r'invoke.*node|call.*node|run.*node', "Direct node invocation"),
        ]
        
        for i, line in enumerate(content.split("\n"), 1):
            for pattern, desc in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Skip if it's clearly not orchestration
                    if "test" in str(file_path).lower():
                        continue
                    if "route" in line.lower():  # Routing functions are OK
                        continue
                    
                    issues.append(LintIssue(
                        file=str(file_path),
                        line=i,
                        column=0,
                        rule=self.rule_id,
                        severity=self.severity,
                        message=f"Possible manual orchestration: {desc}",
                        suggestion="Use StateGraph edges and conditional_edges for flow control",
                    ))
        
        return issues


class MissingErrorHandlingRule(LintRule):
    """Detect nodes without error handling."""
    
    rule_id = "LG003"
    severity = "warning"
    description = "Node functions should have error handling"
    
    def check_file(self, file_path: Path, content: str, tree: ast.AST) -> list[LintIssue]:
        issues = []
        
        # Only check node files
        if "_node" not in str(file_path):
            return issues
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if this looks like a node function
                if not (node.name.endswith("_node") or 
                        (node.args.args and node.args.args[0].arg == "state")):
                    continue
                
                # Check for try/except
                has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
                
                # Check for LLM calls
                has_llm = any(
                    isinstance(n, ast.Call) and 
                    hasattr(n.func, "attr") and 
                    n.func.attr in ("invoke", "ainvoke", "generate", "chat")
                    for n in ast.walk(node)
                )
                
                if has_llm and not has_try:
                    issues.append(LintIssue(
                        file=str(file_path),
                        line=node.lineno,
                        column=node.col_offset,
                        rule=self.rule_id,
                        severity=self.severity,
                        message=f"Node '{node.name}' makes LLM calls without error handling",
                        suggestion="Wrap LLM calls in try/except for graceful error handling",
                    ))
        
        return issues


class StatePollutionRule(LintRule):
    """Detect potential state pollution issues."""
    
    rule_id = "LG004"
    severity = "info"
    description = "State may be accumulating unnecessary data"
    
    def check_file(self, file_path: Path, content: str, tree: ast.AST) -> list[LintIssue]:
        issues = []
        
        # Look for patterns that add to state without cleanup
        patterns = [
            r'state\[[\'"]\w+[\'"]\]\s*=\s*state\.get\([\'"]\w+[\'"].*\)\s*\+',
            r'state\[[\'"]\w+[\'"]\]\.append',
            r'state\[[\'"]\w+[\'"]\]\.extend',
        ]
        
        for i, line in enumerate(content.split("\n"), 1):
            for pattern in patterns:
                if re.search(pattern, line):
                    issues.append(LintIssue(
                        file=str(file_path),
                        line=i,
                        column=0,
                        rule=self.rule_id,
                        severity=self.severity,
                        message="State accumulation detected - ensure this is intentional",
                        suggestion="Consider if accumulated state should be cleaned up at checkpoints",
                    ))
        
        return issues


class MissingTypeHintsRule(LintRule):
    """Detect functions without type hints."""
    
    rule_id = "LG005"
    severity = "info"
    description = "Functions should have type hints"
    
    def check_file(self, file_path: Path, content: str, tree: ast.AST) -> list[LintIssue]:
        issues = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip private functions and tests
                if node.name.startswith("_") or "test" in str(file_path).lower():
                    continue
                
                # Check return type
                if node.returns is None:
                    issues.append(LintIssue(
                        file=str(file_path),
                        line=node.lineno,
                        column=node.col_offset,
                        rule=self.rule_id,
                        severity=self.severity,
                        message=f"Function '{node.name}' missing return type hint",
                        suggestion="Add return type hint for better code documentation",
                    ))
        
        return issues


class HardcodedModelRule(LintRule):
    """Detect hardcoded model names."""
    
    rule_id = "LG006"
    severity = "warning"
    description = "Model names should be configurable"
    
    def check_file(self, file_path: Path, content: str, tree: ast.AST) -> list[LintIssue]:
        issues = []
        
        # Skip config files
        if "config" in str(file_path).lower():
            return issues
        
        # Look for hardcoded model names
        model_pattern = r'["\']gpt-[34][o0]?[-\w]*["\']|["\']claude-[23][-\w]*["\']'
        
        for i, line in enumerate(content.split("\n"), 1):
            if re.search(model_pattern, line, re.IGNORECASE):
                # Skip imports and comments
                if line.strip().startswith("#") or "import" in line:
                    continue
                
                issues.append(LintIssue(
                    file=str(file_path),
                    line=i,
                    column=0,
                    rule=self.rule_id,
                    severity=self.severity,
                    message="Hardcoded model name detected",
                    suggestion="Use environment variable or config for model selection",
                ))
        
        return issues


class UnusedStateFieldsRule(LintRule):
    """Detect potential unused state fields."""
    
    rule_id = "LG007"
    severity = "info"
    description = "State field may be set but never used"
    
    def check_file(self, file_path: Path, content: str, tree: ast.AST) -> list[LintIssue]:
        # This rule requires cross-file analysis, so we'll implement a simple version
        # that looks for fields written in return statements but never read
        
        # Skip non-node files
        if "_node" not in str(file_path):
            return []
        
        issues = []
        
        # Find state fields that are written
        write_pattern = r'return\s*\{[^}]*["\'](\w+)[\'"]\s*:'
        read_pattern = r'state\.get\(["\'](\w+)[\'"]\)|state\[["\'](\w+)[\'"]\]'
        
        written = set(re.findall(write_pattern, content))
        read = set()
        for match in re.finditer(read_pattern, content):
            read.add(match.group(1) or match.group(2))
        
        # Common fields that are expected to be written but read elsewhere
        common_fields = {"messages", "next_prompt", "error", "phase", "current_node"}
        
        potentially_unused = written - read - common_fields
        
        if potentially_unused:
            issues.append(LintIssue(
                file=str(file_path),
                line=1,
                column=0,
                rule=self.rule_id,
                severity=self.severity,
                message=f"State fields may be unused: {', '.join(potentially_unused)}",
                suggestion="Verify these fields are used in other nodes",
            ))
        
        return issues


# =============================================================================
# Linter
# =============================================================================

class AgentLinter:
    """Linter for LangGraph agent projects."""
    
    def __init__(self, config: ToolkitConfig | None = None):
        self.config = config or get_config()
        
        self.rules: list[LintRule] = [
            InlinePromptRule(),
            ManualOrchestrationRule(),
            MissingErrorHandlingRule(),
            StatePollutionRule(),
            MissingTypeHintsRule(),
            HardcodedModelRule(),
            UnusedStateFieldsRule(),
        ]
    
    def lint_file(self, file_path: Path) -> list[LintIssue]:
        """Lint a single file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of issues found
        """
        try:
            content = file_path.read_text()
            tree = ast.parse(content)
        except SyntaxError as e:
            return [LintIssue(
                file=str(file_path),
                line=e.lineno or 1,
                column=e.offset or 0,
                rule="SYNTAX",
                severity="error",
                message=f"Syntax error: {e.msg}",
            )]
        except Exception as e:
            return [LintIssue(
                file=str(file_path),
                line=1,
                column=0,
                rule="READ",
                severity="error",
                message=f"Cannot read file: {e}",
            )]
        
        issues = []
        for rule in self.rules:
            try:
                issues.extend(rule.check_file(file_path, content, tree))
            except Exception as e:
                issues.append(LintIssue(
                    file=str(file_path),
                    line=1,
                    column=0,
                    rule=rule.rule_id,
                    severity="error",
                    message=f"Rule {rule.rule_id} failed: {e}",
                ))
        
        return issues
    
    def lint_directory(self, directory: Path) -> LintReport:
        """Lint all Python files in a directory.
        
        Args:
            directory: Directory to lint
            
        Returns:
            LintReport with all issues
        """
        issues = []
        files_scanned = 0
        
        for file_path in directory.rglob("*.py"):
            # Skip __pycache__
            if "__pycache__" in str(file_path):
                continue
            
            files_scanned += 1
            issues.extend(self.lint_file(file_path))
        
        return LintReport(issues=issues, files_scanned=files_scanned)
    
    def lint_project(self) -> LintReport:
        """Lint the entire project.
        
        Returns:
            LintReport with all issues
        """
        issues = []
        files_scanned = 0
        
        # Lint src directory
        src_dir = self.config.project_root / "src"
        if src_dir.exists():
            report = self.lint_directory(src_dir)
            issues.extend(report.issues)
            files_scanned += report.files_scanned
        
        # Also lint nodes specifically
        nodes_dir = self.config.get_nodes_path()
        if nodes_dir.exists() and nodes_dir != src_dir:
            report = self.lint_directory(nodes_dir)
            issues.extend(report.issues)
            files_scanned += report.files_scanned
        
        # Deduplicate issues (in case directories overlap)
        seen = set()
        unique_issues = []
        for issue in issues:
            key = (issue.file, issue.line, issue.rule)
            if key not in seen:
                seen.add(key)
                unique_issues.append(issue)
        
        return LintReport(issues=unique_issues, files_scanned=files_scanned)


def lint_graph(
    config: ToolkitConfig | None = None,
    verbose: bool = False,
) -> LintReport:
    """Lint the graph project (sync wrapper).
    
    Args:
        config: Optional toolkit configuration
        verbose: Include suggestions in output
        
    Returns:
        LintReport with all issues
    """
    linter = AgentLinter(config)
    return linter.lint_project()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="agent_lint - Static analysis for LangGraph agents",
    )
    
    parser.add_argument(
        "path",
        nargs="?",
        help="File or directory to lint (default: entire project)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show suggestions for each issue",
    )
    parser.add_argument(
        "--config",
        help="Path to config file",
    )
    parser.add_argument(
        "--project-root",
        help="Project root directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--rules",
        action="store_true",
        help="List available lint rules",
    )
    
    args = parser.parse_args()
    
    # Setup config
    if args.config:
        config = ToolkitConfig.from_file(args.config)
    else:
        config = ToolkitConfig.from_env()
    
    if args.project_root:
        config.project_root = Path(args.project_root)
    
    set_config(config)
    
    linter = AgentLinter(config)
    
    # List rules
    if args.rules:
        print("Available lint rules:")
        for rule in linter.rules:
            print(f"  {rule.rule_id}: {rule.description} [{rule.severity}]")
        return
    
    # Run linter
    if args.path:
        path = Path(args.path)
        if path.is_file():
            issues = linter.lint_file(path)
            report = LintReport(issues=issues, files_scanned=1)
        else:
            report = linter.lint_directory(path)
    else:
        report = linter.lint_project()
    
    if args.json:
        import json
        data = {
            "files_scanned": report.files_scanned,
            "errors": report.error_count,
            "warnings": report.warning_count,
            "info": report.info_count,
            "issues": [
                {
                    "file": i.file,
                    "line": i.line,
                    "column": i.column,
                    "rule": i.rule,
                    "severity": i.severity,
                    "message": i.message,
                    "suggestion": i.suggestion,
                }
                for i in report.issues
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        print(report.format_report(verbose=args.verbose))
    
    # Exit with error if there are errors
    sys.exit(1 if report.error_count > 0 else 0)


if __name__ == "__main__":
    main()
