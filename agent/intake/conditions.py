"""Map how veterans describe a condition to the VA-style name used downstream.

Veterans say "ringing in my ears"; the VA (and the firm's face notes) say "tinnitus". The same
normalisation is needed again in case prep when matching intake conditions to the C-file, so it
lives in one place. The table is deliberately small and conservative: an unknown phrase passes
through cleaned up but unchanged, and is never silently merged into a different condition.
"""

from __future__ import annotations

import re

# canonical name -> phrases that mean it (matched as whole words, longest phrase first)
SYNONYMS: dict[str, list[str]] = {
    "tinnitus": [
        "ringing in my ears",
        "ringing in the ears",
        "ears ringing",
        "ringing ears",
        "ringing",
        "tinnitus",
    ],
    "bilateral hearing loss": [
        "bilateral hearing loss",
        "hearing loss",
        "trouble hearing",
        "can't hear well",
        "bl hl",
    ],
    "ptsd": [
        "post traumatic stress disorder",
        "post-traumatic stress",
        "posttraumatic stress",
        "ptsd",
    ],
    "depression": ["major depressive disorder", "depression", "mdd"],
    "anxiety": ["generalized anxiety disorder", "anxiety", "gad"],
    "sleep apnea": ["obstructive sleep apnea", "stop breathing at night", "sleep apnea", "osa"],
    "migraines": ["migraine headaches", "migraines", "migraine", "headaches"],
    "hypertension": ["high blood pressure", "hypertension", "htn"],
    "gerd": ["acid reflux", "heartburn", "reflux", "gerd"],
    "lumbar strain": [
        "lower back pain",
        "low back pain",
        "bad back",
        "back pain",
        "lower back",
        "lumbar strain",
        "back",
    ],
    "cervical strain": ["neck pain", "cervical strain", "neck"],
    "right knee condition": ["right knee"],
    "left knee condition": ["left knee"],
    "bilateral knee condition": ["both knees", "bilateral knees", "knees"],
    "right shoulder condition": ["right shoulder"],
    "left shoulder condition": ["left shoulder"],
    "erectile dysfunction": ["erectile dysfunction", "ed"],
    "diabetes mellitus type 2": ["type 2 diabetes", "diabetes"],
    "prostate cancer": ["prostate cancer"],
    "plantar fasciitis": ["plantar fasciitis", "foot pain", "feet hurt"],
}

_PHRASES: list[tuple[str, str]] = sorted(
    ((phrase, canon) for canon, phrases in SYNONYMS.items() for phrase in phrases),
    key=lambda pc: len(pc[0]),
    reverse=True,
)

_FILLER = re.compile(r"^(my|the|a|an|some|really|bad|chronic)\s+", re.IGNORECASE)


def normalize_condition(text: str) -> str:
    """Return the canonical name for one condition phrase, or the cleaned phrase if unknown."""
    cleaned = re.sub(r"\s+", " ", text.strip().strip(".").lower())
    for phrase, canon in _PHRASES:
        if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", cleaned):
            return canon
    while _FILLER.match(cleaned):
        cleaned = _FILLER.sub("", cleaned, count=1)
    return cleaned


def normalize_conditions(items: list[str]) -> list[str]:
    """Normalise and de-duplicate, keeping first-mention order."""
    out: list[str] = []
    for item in items:
        name = normalize_condition(item)
        if name and name not in out:
            out.append(name)
    return out
