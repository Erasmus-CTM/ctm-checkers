def test(check, symbols):
    def score(n,edges):
        nodes = [{"id": i,"x": i,"y": 0} for i in range(n)]
        return check({"representation": "undirected-graph", "nodes": nodes, "edges": edges}, symbols)["score"]
    good = [[0, 1], [0, 2], [0, 3], [0, 4], [1, 2], [1, 3], [1, 4], [2, 3], [2, 4], [3, 4]]
    assert score(5,good) == 1
    assert score(5,list(reversed(good))) == 1
    assert score(5,[[0, 1], [1, 2], [2, 3], [3, 4]]) < 1
    assert score(6,good) == 1
    assert score(0,[]) == 0
    assert score(5,good+[[0,99]]) == 0
    assert score(6,[[i,j] for i in range(3) for j in range(3,6)]) == 1
    # A triangular prism is planar despite having six vertices and nine edges.
    assert score(6,[[0,1],[1,2],[2,0],[3,4],[4,5],[5,3],[0,3],[1,4],[2,5]]) < 1
