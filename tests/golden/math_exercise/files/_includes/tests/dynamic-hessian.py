def test(check, symbols):
    def score(H):
        return check({"inputs": {"H": {"matrix": H}}}, symbols)["score"]
    H = Matrix([[2,1,0],[1,4,1],[0,1,6]])
    assert score(H) == 1
    assert score(eye(2)) == 0
    assert score(H+eye(3)) == 0
    H[0,1] = 0
    assert 0 < score(H) < 1
