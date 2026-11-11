"""Tutoring engine prototype.

Generates simple lessons and exercises from a topic label using KG and mapping.
"""
from typing import Dict, Any


def generate_lesson(topic: str, level: str = "intro") -> Dict[str, Any]:
    # Simple stub: produce a few learning objectives and exercises.
    if level == "intro":
        objectives = [
            f"Understand the core concepts of {topic}",
            "Learn key definitions and historical context",
            "Read foundational papers or summaries"
        ]
        exercises = [
            {"q": f"Explain in your own words: What is {topic}?", "points": 5},
            {"q": f"List three core concepts related to {topic} and briefly describe them.", "points": 10}
        ]
    else:
        objectives = [f"Deepen understanding of advanced {topic} topics"]
        exercises = [{"q": f"Implement or derive an advanced result about {topic}", "points": 20}]

    return {"topic": topic, "level": level, "objectives": objectives, "exercises": exercises}
