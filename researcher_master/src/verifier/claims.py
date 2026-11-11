import re
from typing import List


def extract_claims(text: str) -> List[str]:
    """Very small, conservative claim extractor used for tests and local runs.

    Strategy:
    - Split text into sentences using simple punctuation rules.
    - Filter out very short or clearly subjective sentences.
    - Return the remaining sentences as candidate claims (trimmed).
    This is intentionally conservative and deterministic.
    """
    if not text:
        return []

    # split on sentence-like punctuation
    sentences = re.split(r'(?<=[\.\!\?])\s+', text.strip())
    claims = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        s_clean = s.rstrip('.!?')
        # skip very short lines and clearly subjective hedges
        if len(s_clean.split()) < 4:
            continue
        low = s_clean.lower()
        if any(hedge in low for hedge in ['i think', 'i believe', "in my opinion", 'maybe', 'probably']):
            # still include if there are other informative words, but prefer to exclude
            continue
        claims.append(s_clean)

    return claims
