from typing import Optional, NamedTuple, Set

from citegraph.draw import Graph
from citegraph.model import Biblio, Paper, PaperId
from citegraph.semapi import PaperDb, PaperAndRefs


class Params(NamedTuple):
    """
    Parameters of the graph exploration.

    The degree of interest (DOI) of a paper is determined roughly
    according to the following formula:

      DOI(n) = api_weight * API(n) - distance_penalty * distance(n)

    where API, the a-priori interest in a paper, is a function of the
    edges that the paper would create in the graph if it is included.
    The API is roughly computed like so:

      API(n) = min(degree(n), degree_cut) * (1 + clustering_factor * clustering_coefficient(n))

    The first factor is a measure of the raw number of edges that
    the paper would add to the graph. In order not to favor very
    influential papers over lesser known ones, and not to create
    too many edges (which would make the graph unreadable), this
    is cut above the degree_cut parameter.

    The second term scales the first according to a measure of the
    clustering between the node and its neighbors. It favors nodes
    that are tightly clustered with their neighbors over nodes that
    form unrelated connections with the whole graph.

    In the DOI formula, the distance metric is a measure of the shortest
    directed path between a paper and any root of the graph. Paths
    that go through papers that were found in the bibliography are
    artificially shortened, the point being to favor nodes that are
    closer to the papers in the bibliography. Edges are weighted by
    a "cost" metric, a lower cost being assigned to edges that connect
    similar papers. The similarity metric used for this uses only
    shared authors for now.

    Attributes:
    - api_weight

        The weight given to the API  when computing the DOI (degree of interest)

    - degree_cut (> 0)

        Degree above which all nodes are treated equally. This makes it so, that not only
        very influential papers are included in the graph. A lower value favors papers that
        don't have many citations.

    - clustering_factor (>= 0)

        Importance given to the clustering coefficient of a node when computing its API.

    - distance_penalty

        Coefficient applied to the distance metric before it is subtracted from the API to compute the DOI.
        - A value > 0 means distance from the root is penalized (typical)
        - A value of zero means distance from the root has no effect at all on DOI
        - A value < 0 means distance from the root is rewarded

    - api_failure_limit

        Number of failures to tolerate from the semanticscholar API before the exploration is aborted.

    - max_graph_size

        Max number of nodes to include on the graph

    """

    distance_penalty: float = 0.2
    degree_cut: int = 3  # > 0
    clustering_factor: float = 0.5  # > 0
    api_weight: float = 1  # > 0

    api_failure_limit: int = 10
    max_graph_size: int = 80
    consider_upward_links: bool = False



Infty = 2 ** 1000


def authors_in_common(p1: Paper, p2: Paper) -> int:
    return len(author_set(p1) & author_set(p2))


def authors_similarity(p1: Paper, p2: Paper) -> float:
    num_authors = min(len(p1.authors), len(p2.authors))
    if num_authors == 0:
        return 1
    return authors_in_common(p1, p2) / num_authors


def author_set(p1):
    return {" ".join(p.last_names) for p in p1.authors}


def clusterness(neighbors_in_graph, neighbors):
    # https://en.wikipedia.org/wiki/Clustering_coefficient
    num_neighbors = len(neighbors_in_graph)
    total_possible_triplets = num_neighbors * (num_neighbors - 1) / 2

    if total_possible_triplets == 0:
        return 0.75


    def are_neighbors(src: PaperId, dst: PaperId):
        return dst in neighbors[src] if src in neighbors else False


    closed_triplets = sum(1
                          for (i, nid) in enumerate(neighbors_in_graph)
                          for (j, mid) in enumerate(neighbors_in_graph)
                          if i < j and are_neighbors(nid, mid))

    return closed_triplets / total_possible_triplets



def smart_fetch(seeds: Set[PaperId],
                biblio: Biblio,
                params: Params,
                db: PaperDb) -> Graph:
    """
    Builds the graph by fetching reference data from semapi.

    """

    assert len(seeds) > 0

    nodes = {}
    neighbors = {}  # merged successors + predecessors
    influential_edges = set([])

    request_failures = 0
    failed_ids = set([])


    def handle_api_failure(id: PaperId, p: Optional[Paper]):
        nonlocal request_failures
        print("[ERROR] Scholar doesn't know paper with id %s (%s)" % (id, p and p.title or "unknown title"))
        if id in nodes:  # may not be here if the ID is a root
            del nodes[id]
        failed_ids.add(id)
        request_failures += 1
        if request_failures > params.api_failure_limit:
            print(f"[ERROR] Too many failures of semanticscholar API (> {params.api_failure_limit})")
            print(f"        This may mean you hit the API's rate limit")
            print(f"        Aborting.")
            return True
        return False


    def edge_disinterest(src: Paper, dst: Paper) -> float:
        """ > 0"""
        max_disinterest = 5
        return 1 + max_disinterest * (1 - authors_similarity(src, dst))


    def update_multimap(k, v):
        if k in neighbors:
            neighbors_of_k = neighbors[k]
            if v not in neighbors_of_k:
                neighbors_of_k.add(v)
                return True
            else:
                return False
        else:
            neighbors[k] = {v}
            return True


    def add_ref(src, dst, is_influential):
        """Record that paper src cites paper dst."""
        if update_multimap(dst.id, src.id):
            if is_influential:
                influential_edges.add((src.id, dst.id))
            return update_multimap(src.id, dst.id)
        return False


    def a_priori_interest(p: Paper) -> float:
        """a-priori interest in the paper"""
        my_neighbors = neighbors.get(p.id, set())
        neighbors_in_graph = graph_nodes.keys() & my_neighbors
        num_new_edges = len(neighbors_in_graph)

        clustering = params.clustering_factor * clusterness(neighbors_in_graph, neighbors)
        base = min(num_new_edges, params.degree_cut) * (1 + clustering)

        influence_bonus = sum((+2 if (src in neighbors_in_graph and dst == p.id)
                                   else +1 if (dst in neighbors_in_graph and src == p.id) else 0)
                               for (src, dst) in influential_edges
                               ) / (num_new_edges + 1)
        # if influence_bonus != 0:
        #     print(f"{influence_bonus} / {(num_new_edges + 1)} = {influence_bonus / (num_new_edges + 1)}")

        base = base + influence_bonus

        return base * 3 if p in biblio else base


    def distance_from_focal(p: Paper):
        return distance_to_root.get(p.id, 10)


    def degree_of_interest(p: Paper) -> float:
        return params.api_weight * a_priori_interest(p) \
               - params.distance_penalty * distance_from_focal(p)


    def update_distances(cur, neighbor):
        # Try to see if passing through the new neighbor is a better path from the root to 'cur'
        best_dist = distance_to_root.get(cur.id, Infty)
        tentative_dist = distance_to_root.get(neighbor.id, Infty) + edge_disinterest(neighbor, cur)
        if tentative_dist < best_dist:
            distance_to_root[cur.id] = tentative_dist
            best_dist = tentative_dist

        # Similarly, try to see if passing through 'cur' is a better path from the root to the neighbor
        tentative_dist = best_dist + edge_disinterest(cur, neighbor)
        cur_dist = distance_to_root.get(neighbor.id, Infty)
        if tentative_dist < cur_dist:
            distance_to_root[neighbor.id] = tentative_dist


    def update_graph(cur):

        for (citing, is_influential) in sorted(cur.citations, key=lambda c: c.paper.id):
            nodes[citing.id] = citing
            if add_ref(citing, cur, is_influential) and params.consider_upward_links:
                # only if we really added the ref
                update_distances(citing, cur)

        for (cited, is_influential) in sorted(cur.references, key=lambda c: c.paper.id):
            nodes[cited.id] = cited
            if add_ref(cited, cur, is_influential):
                # only if we really added the ref
                update_distances(cur, cited)


    # fetch the roots
    roots = [resp for id in seeds for resp in [db.fetch_from_id(id)] if resp or not handle_api_failure(id, None)]
    roots = [r for r in roots if r]
    if len(roots) == 0:
        print("[ERROR] No roots could be fetched")
        return Graph({})

    # For node n, g_score[n] is the cost of the best path from start to n currently known.
    distance_to_root = {p.id: 0 for p in roots}
    nodes = {**nodes, **{p.id: p for p in roots}}
    # Nodes that are in the graph
    graph_nodes = {}

    for r in roots:
        update_graph(r)

    # todo dynamic programming
    #  the DOI of a node doesn't change unless the node's neighbors have changed
    while True:
        (best, cur_doi) = max([(n, degree_of_interest(n))
                               for n in nodes.values()
                               if n.id not in graph_nodes
                               and n.id not in failed_ids],
                              key=lambda t: t[1],
                              default=(None, 0))
        if not best:
            print("No more nodes to explore")
            break  # no more nodes

        pre_id = best.id
        result: Optional[PaperAndRefs] = db.fetch_from_id(best.id) if not isinstance(best, PaperAndRefs) else best

        if not result:
            if handle_api_failure(best.id, best):
                break
            continue

        best = result
        graph_nodes[best.id] = best
        if pre_id != best.id:
            del nodes[pre_id]
            if pre_id in graph_nodes:
                del graph_nodes[pre_id]

        print(f'[{len(graph_nodes)} / {params.max_graph_size} / {len(nodes)}] (DOI {cur_doi}) {best.title} ')
        if len(graph_nodes) >= params.max_graph_size:
            print("Hit max size threshold")
            break

        update_graph(best)

    return Graph(graph_nodes)
