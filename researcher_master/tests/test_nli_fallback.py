from src.verifier.nli import predict_entailment


def test_nli_fallback_shape():
    res = predict_entailment("Water boils at 100°C at sea level.", "Water boils at 100 degrees Celsius.")
    assert isinstance(res, dict)
    assert 'label' in res and 'score' in res
    assert res['label'] in ('ENTAILMENT', 'CONTRADICTION', 'NEUTRAL')
    assert isinstance(res['score'], float)
    assert 0.0 <= res['score'] <= 1.0
