"""Utility functions for agent toolkit."""


def format_duration(ms: float) -> str:
    """Format duration in human-readable form.
    
    Args:
        ms: Duration in milliseconds
        
    Returns:
        Formatted string
    """
    if ms < 1000:
        return f"{ms:.1f}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        return f"{ms/60000:.1f}m"


def format_cost(cost: float) -> str:
    """Format cost with appropriate precision.
    
    Args:
        cost: Cost in dollars
        
    Returns:
        Formatted string
    """
    if cost < 0.0001:
        return f"${cost:.6f}"
    elif cost < 0.01:
        return f"${cost:.4f}"
    else:
        return f"${cost:.2f}"


def format_tokens(tokens: int) -> str:
    """Format token count with commas.
    
    Args:
        tokens: Token count
        
    Returns:
        Formatted string
    """
    return f"{tokens:,}"


def truncate_string(s: str, max_len: int = 100, suffix: str = "...") -> str:
    """Truncate string to max length.
    
    Args:
        s: String to truncate
        max_len: Maximum length
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated string
    """
    if len(s) <= max_len:
        return s
    return s[:max_len - len(suffix)] + suffix


def sanitize_for_display(text: str) -> str:
    """Sanitize text for terminal display.
    
    Removes or escapes control characters.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text
    """
    # Remove common control characters
    result = text.replace("\r", "")
    result = result.replace("\t", "    ")
    # Remove ANSI escape codes if present in source
    import re
    result = re.sub(r'\x1b\[[0-9;]*m', '', result)
    return result


def redact_secrets(text: str) -> str:
    """Redact potential secrets from text.
    
    Args:
        text: Text that may contain secrets
        
    Returns:
        Text with secrets redacted
    """
    import re
    
    # Patterns for common secrets
    patterns = [
        (r'(sk|api|key|token|secret|password|auth)[_-]?[a-zA-Z0-9]{16,}', '[REDACTED]'),
        (r'Bearer\s+[a-zA-Z0-9._-]+', 'Bearer [REDACTED]'),
        (r'(?i)(password|passwd|pwd)\s*[=:]\s*\S+', r'\1=[REDACTED]'),
    ]
    
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def calculate_percentage_change(old: float, new: float) -> str:
    """Calculate and format percentage change.
    
    Args:
        old: Old value
        new: New value
        
    Returns:
        Formatted change string
    """
    if old == 0:
        if new == 0:
            return "0%"
        return "+∞"
    
    change = ((new - old) / old) * 100
    
    if change > 0:
        return f"+{change:.1f}%"
    else:
        return f"{change:.1f}%"


def create_progress_bar(progress: float, width: int = 30, filled: str = "█", empty: str = "░") -> str:
    """Create a text progress bar.
    
    Args:
        progress: Progress from 0.0 to 1.0
        width: Bar width in characters
        filled: Character for filled portion
        empty: Character for empty portion
        
    Returns:
        Progress bar string
    """
    progress = max(0.0, min(1.0, progress))
    filled_width = int(progress * width)
    return filled * filled_width + empty * (width - filled_width)
