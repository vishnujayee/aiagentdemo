from src.verifier.claims import extract_claims


def test_extract_claims_basic():
    text = (
        "Photosynthesis is the process by which plants convert sunlight into chemical energy. "
        "It occurs in chloroplasts. I think it's essential for life on Earth."
    )
    claims = extract_claims(text)
    assert isinstance(claims, list)
    # should extract at least one substantive claim about photosynthesis
    assert any("Photosynthesis" in c or "photosynthesis" in c.lower() for c in claims)
