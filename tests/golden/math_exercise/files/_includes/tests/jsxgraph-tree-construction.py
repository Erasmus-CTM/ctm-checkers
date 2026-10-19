def test(check, symbols):
    def score(n,edges):
        nodes = [{"id": i,"x": i,"y": 0} for i in range(n)]
        return check({"representation": "undirected-graph", "nodes": nodes, "edges": edges}, symbols)["score"]
    good = [[0, 1], [1, 2], [2, 3], [3, 4]]
    assert score(5,good) == 1
    assert score(5,list(reversed(good))) == 1
    assert score(5,[[0, 1], [1, 2], [2, 0], [3, 4]]) < 1
    assert score(6,good) < 1
    assert score(0,[]) == 0
    assert score(5,good+[[0,99]]) == 0
