"""Graph-editor answers as NetworkX graphs (math-exercise 0.10.0's
graph_from_response, moved verbatim; NetworkX is imported when it is used)."""


def graph_from_response(response, *, directed=False):
    """Validate graph-editor JSON and return a NetworkX graph."""
    import math as _graph_math
    import networkx as nx

    if not isinstance(response, dict):
        raise ValueError("Graph response must be an object")
    expected = "directed-graph" if directed else "undirected-graph"
    if response.get("representation") != expected:
        raise ValueError(f"Expected {expected} response")
    nodes = response.get("nodes")
    edges = response.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Graph response needs node and edge lists")

    graph = nx.DiGraph() if directed else nx.Graph()
    known = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("Every graph node must be an object")
        node_id = node.get("id")
        if type(node_id) is not int or node_id in known:
            raise ValueError("Graph node identifiers must be unique integers")
        try:
            x, y = float(node["x"]), float(node["y"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Every graph node needs numeric x and y coordinates")
        if not _graph_math.isfinite(x) or not _graph_math.isfinite(y):
            raise ValueError("Graph node coordinates must be finite")
        known.add(node_id)
        graph.add_node(node_id, x=x, y=y)

    seen = set()
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise ValueError("Every graph edge must contain two endpoints")
        source, target = edge
        if source not in known or target not in known or source == target:
            raise ValueError("Graph edges need two distinct known endpoints")
        key = (source, target) if directed else tuple(sorted((source, target)))
        if key in seen:
            raise ValueError("Graph response contains a duplicate edge")
        seen.add(key)
        graph.add_edge(source, target)
    return graph
