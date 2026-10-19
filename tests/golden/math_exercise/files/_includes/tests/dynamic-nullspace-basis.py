def test(check, symbols):
    def score(B):
        return check({"inputs": {"Z": {"matrix": B}}}, symbols)["score"]
    B = Matrix([[-2, -3], [1, 0], [0, 1]])
    assert score(B) == 1
    assert score(B[:, ::-1]) == 1
    incomplete = B[:, :1]
    assert 0 < score(incomplete) < 1
    dependent = B.row_join(B[:, :1])
    assert score(dependent) < 1
    assert score(zeros(B.rows,B.cols)) == 0
    assert score(I*B) < 1
    assert score(zeros(0,0)) == 0
    # Typed decimals are exact; a typed 0.0 column is still the zero vector.
    decimal = Matrix([[Float("-0.3"), -2], [0, 1], [Float("0.1"), 0]])
    assert score(decimal) == 1
    zero_column = B.row_join(Matrix([Float("0.0")]*3))
    result = check({"inputs": {"Z": {"matrix": zero_column}}}, symbols)
    assert result["assessment"]["Z"]["columns"][-1] == "incorrect"
