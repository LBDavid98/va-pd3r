"""Prompt template utilities."""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader

_template_dir = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(_template_dir))


def get_template(name: str):
    """Load a Jinja2 template by name."""
    return _env.get_template(name)
