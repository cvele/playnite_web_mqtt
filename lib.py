def make_human_friendly(topic_base: str) -> str:
    """Make the topic base more human-readable."""
    parts = topic_base.split("/")[-1]
    parts = parts.replace("_", " ")
    return parts.title()
