def make_human_friendly(topic_base: str) -> str:
    """Make the topic base more human-readable."""
    parts = topic_base.split('/')[-1]  # Get the last part after the slash
    parts = parts.replace('_', ' ')  # Replace underscores with spaces
    return parts.title()
