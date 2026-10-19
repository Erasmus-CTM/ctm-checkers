def test(check, symbols):
    def score(B):
        return check({"inputs": {"R": {"matrix": B}}}, symbols)["score"]
    B = Matrix([[1, 0, 1, 2], [0, 1, 1, 1]])
    assert score(B) == 1
    assert score(B[::-1, :]) == 1
    incomplete = B[:1, :]
    assert 0 < score(incomplete) < 1
    dependent = B.col_join(B[:1, :])
    assert score(dependent) < 1
    assert score(zeros(B.rows,B.cols)) == 0
    assert score(I*B) < 1
    assert score(zeros(0,0)) == 0
    # Typed decimals are exact.
    assert score(Matrix([[Float("0.1"), 0, Float("0.1"), Float("0.2")], [0, 1, 1, 1]])) == 1
