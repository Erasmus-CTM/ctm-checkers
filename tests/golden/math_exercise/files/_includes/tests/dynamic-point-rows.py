def test(check, symbols):
    def score(rows):
        return check({"inputs": {"P": {"matrix": Matrix(rows)}}}, symbols)["score"]
    assert score([[0,0],[1,2]]) == 1
    assert score([[1,2],[1,2]]) < 1
    assert score([[I,2*I],[2*I,4*I]]) < 1
    assert score([[1,3],[2,4]]) < 1
    assert score([[1,2],[sin(1)**2+cos(1)**2,2]]) < 1
