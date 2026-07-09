"""Small shared utilities."""

import os


def project_root():
    """The project root (contains home_config.json, svg_examples/)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def clean_num(text):
    """Strip whitespace and a trailing unit suffix from a numeric text field."""
    return text.strip().replace("mm", "").replace("px", "").strip()
