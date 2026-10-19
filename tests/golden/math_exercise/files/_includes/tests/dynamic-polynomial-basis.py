def test(check, symbols):
    def score(B):
        return check({"inputs": {"Pcoef": {"matrix": B}}}, symbols)["score"]
    B = Matrix([[-3, 2], [2, -3], [1, 0], [0, 1]])
    assert score(B) == 1
    assert score(B[:, ::-1]) == 1
    incomplete = B[:, :1]
    assert 0 < score(incomplete) < 1
    dependent = B.row_join(B[:, :1])
    assert score(dependent) < 1
    assert score(zeros(B.rows,B.cols)) == 0
    assert score(I*B) < 1
    assert score(zeros(0,0)) == 0
    # Typed decimals are exact: 0.1 + 0.2 - 0.3 is exactly zero.
    assert score(Matrix([[Float("-0.3"), 2], [Float("0.2"), -3], [Float("0.1"), 0], [0, 1]])) == 1
