def test(check, symbols):
    def score(n,edges):
        nodes = [{"id": i,"x": i,"y": 0} for i in range(n)]
        return check({"representation": "undirected-graph", "nodes": nodes, "edges": edges}, symbols)["score"]
    good = [[0, 1], [1, 2], [2, 3], [3, 0]]
    assert score(4,good) == 1
    assert score(4,list(reversed(good))) == 1
    assert score(4,[[0, 1], [1, 2], [2, 0], [2, 3]]) < 1
    # The four-cycle plus an isolated vertex still has a closed trail through every edge.
    assert score(5,good) == 1
    # Two disjoint triangles have even degrees, but no single closed trail uses both.
    assert score(6,[[0,1],[1,2],[2,0],[3,4],[4,5],[5,3]]) < 1
    assert score(0,[]) == 0
    assert score(4,good+[[0,99]]) == 0
