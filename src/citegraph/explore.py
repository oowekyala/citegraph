from queue import PriorityQueue
from typing import List, Optional, NamedTuple

from citegraph.model import Biblio, Paper, PaperId
from citegraph.draw import Graph
from citegraph.semapi import PaperDb, PaperAndRefs

Infty = 2 ** 1000

def age(p: Paper):
    return 2020 - int(p.year or 2000)

def authors_in_common(p1: Paper, p2: Paper) -> int:
    return len(author_set(p1) & author_set(p2))


def authors_similarity(p1: Paper, p2: Paper) -> float:
    return (1 + authors_in_common(p1, p2)) / (1 + min(len(p1.authors), len(p2.authors)))


def author_set(p1):
    return {" ".join(p.last_names) for p in p1.authors}


def seeds_in_bib(biblio: Biblio):
    seeds = []
    for paper in biblio:
        if paper.paperId:
            seeds.append(paper.paperId)
        elif paper.journal and paper.journal.lower() == "arxiv":
            volume: str = getattr(paper, "volume", "")
            if volume.startswith("abs/"):
                seeds.append("arXiv:" + volume[len("abs/"):])

    return seeds



class Params(NamedTuple):
    api_weight: float  # > 0
    distance_penalty: float  # < 0
    degree_cut: int  # > 0
    clustering_factor: float  # > 0



DEFAULT_PARAMS = Params(api_weight=1,
                        distance_penalty=-1.5,
                        degree_cut=5,
                        clustering_factor=1
                        )



def clusterness(neighbors_in_graph, neighbors):
    if len(neighbors_in_graph) == 0:
        return 1


    def are_neighbors(src: PaperId, dst: PaperId):
        return dst in neighbors.get(src, [])


    closed_triplets = 0

    # This `if i < j` is quite shitty, but we use sets.
    for i, nid in enumerate(neighbors_in_graph):
        for j, mid in enumerate(neighbors_in_graph):
            if i < j and are_neighbors(nid, mid):
                closed_triplets += 1

    total_possible_triplets = len(neighbors_in_graph) * (len(neighbors_in_graph) + 1) / 2

    return closed_triplets / total_possible_triplets



def smart_fetch(seeds: List[PaperId],
                biblio: Biblio,
                max_size: int,
                db: PaperDb) -> Optional[Graph]:
    """
    Builds the initial graph by fetching reference data from semapi.
    This does some heuristic search to find papers that are the "closest"
    from the bibliography entries.

    :param seeds: Ids of the papers to start the search with
    :param biblio: Bib file
    :param max_size: Maximum number of nodes
    :param db: API to get references
    :return:
    """

    params = DEFAULT_PARAMS

    # Complete the given seeds with seeds from the bibtex file
    seeds = {*seeds, *seeds_in_bib(biblio)}

    if len(seeds) == 0:
        print("Cannot find seeds, mention some paper ids on the command line?")
        return None

    request_failures = 0
    FAILURE_LIMIT = 10

    def exception_handler(request, exception):
        nonlocal request_failures
        request_failures += 1
        print("Request failed %s %s" % (str(request), str(exception)))  # todo
        if request_failures > FAILURE_LIMIT:
            print("API limit reached, aborting")


    def edge_disinterest(src: Paper, dst: Paper) -> float:
        """ > 0"""
        max_disinterest = 5
        return 1 + max_disinterest * (1 - authors_similarity(src, dst))


    neighbors = {}  # merged successors + predecessors


    def update_multimap(map, k, v):
        if k in map:
            map[k].add(v)
        else:
            map[k] = {v}


    def add_ref(src, dst):
        """Record that paper src cites paper dst."""
        update_multimap(neighbors, dst.id, src.id)
        update_multimap(neighbors, src.id, dst.id)

    def api(p: Paper) -> float:
        """a-priori interest in the paper"""
        if p.id == 'bdc3d618db015b2f17cd76224a942bfdfc36dc73':
            # https://www.semanticscholar.org/paper/Intravenous-Oxycodone-Versus-Other-Intravenous-for-Raff-Belbachir/bdc3d618db015b2f17cd76224a942bfdfc36dc73
            # Buggy article (224K citations)
            return -1000

        my_neighbors = neighbors.get(p.id, set())
        neighbors_in_graph = graph_nodes.keys() & my_neighbors
        num_new_edges = len(neighbors_in_graph)

        # my_age = age(p)
        # avg_age_diff = sum([abs(my_age - age(graph_nodes[id])) for id in neighbors_in_graph]) / (1 + num_new_edges)

        clustering = params.clustering_factor * clusterness(neighbors_in_graph, neighbors)
        base = min(num_new_edges, params.degree_cut) * (1 + clustering)

        return base * 3 if p in biblio else base

    def distance_from_focal(p: Paper):
        return distance_to_root.get(p.id, 10)


    def degree_of_interest(p: Paper) -> float:
        return params.api_weight * api(p) \
               + params.distance_penalty * distance_from_focal(p)


    def update_graph(cur):
        for citing in cur.citations:
            nodes[citing.id] = citing
            add_ref(citing, cur)

        for cited in cur.references:
            nodes[cited.id] = cited
            add_ref(cur, cited)

            # Try to see if passing through the new neighbor is a better path from the root to 'best'
            best_dist = distance_to_root.get(cur.id, Infty)
            tentative_dist = distance_to_root.get(cited.id, Infty) + edge_disinterest(cited, cur)
            if tentative_dist < best_dist:
                distance_to_root[cur.id] = tentative_dist
                best_dist = tentative_dist

            # Similarly, try to see if passing through 'best' is a better path from the root to the neighbor
            tentative_dist = best_dist + edge_disinterest(cur, cited)
            cur_dist = distance_to_root.get(cited.id, Infty)
            if tentative_dist < cur_dist:
                distance_to_root[cited.id] = tentative_dist


    # fetch the roots
    roots = db.batch_fetch(seeds, exhandler=exception_handler)

    # For node n, g_score[n] is the cost of the best path from start to n currently known.
    distance_to_root = {p.id: 0 for p in roots}
    nodes = {p.id: p for p in roots}
    graph_nodes = {}

    for r in roots:
        update_graph(r)

    failed_ids = set([])

    # todo dynamic programming
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
        result: Optional[PaperAndRefs] = db.fetch_from_id(best.id)

        if not result:
            print("Scholar doesn't know paper with id %s" % best.id)
            del nodes[best.id]
            failed_ids.add(best.id)
            request_failures += 1
            if request_failures > FAILURE_LIMIT:
                print("API limit reached, aborting")
                break
            continue

        best = result
        graph_nodes[best.id] = best
        if pre_id != best.id:
            del nodes[pre_id]
            if pre_id in graph_nodes:
                del graph_nodes[pre_id]

        print(f'[{len(graph_nodes)} / {max_size} / {len(nodes)}] (DOI {cur_doi}) {best.title} ')
        if len(graph_nodes) >= max_size:
            print("Hit max size threshold")
            break

        update_graph(best)

    return Graph(graph_nodes)



# TODO remove me
def initialize_graph(seeds: List[PaperId],
                     biblio: Biblio,
                     max_size: int,
                     db: PaperDb) -> Graph:
    """
    Builds the initial graph by fetching reference data from semapi.
    This does some heuristic search to find papers that are the "closest"
    from the bibliography entries.

    TODO consider seeds

    TODO expand on that by reweighting nodes according to eg in-degree
        Eg the references of a widely cited paper are more important than one-off reference chains
        References of the root should not be too overweighted

    :param seeds: Ids of the papers to start the search with
    :param biblio: Bib file
    :param max_size: Maximum number of nodes
    :param db: API to get references
    :return:
    """


    def cost(paper: Paper):
        return 8 if paper in biblio else 20


    def edge_cost(src: Paper, dst: Paper) -> int:
        base = 8
        if src in biblio:
            base = 6
        elif dst in biblio:
            base = 7
        # the minimum edge weight must be positive
        return base - min(authors_in_common(src, dst), 3)


    open_set = PriorityQueue()

    seeds = [*seeds, *seeds_in_bib(biblio)]

    # For node n, g_score[n] is the cost of the best path from start to n currently known.
    g_score = {id: 0 for id in seeds}

    # For node n, f_score[n] := g_score[n] + h(n). f_score[n] represents our current best guess as to
    # how short a path from start to finish can be if it goes through n.
    f_score = {id: 8 for id in seeds}

    nodes = {}


    def push(id: PaperId):
        f = f_score[id]
        open_set.put((f, id))


    def is_not_in_open_set(p: Paper):
        for (_, c) in open_set.queue:
            if c == p.id:
                return False
        return True


    for e in seeds:
        push(e)

    failures = 0

    while open_set.qsize() > 0:
        (cur_f_score, paper_id) = open_set.get()

        result: Optional[PaperAndRefs] = db.fetch_from_id(paper_id)

        if not result:
            print("Scholar doesn't know paper with id %s" % paper_id)
            failures += 1
            if failures > 10:
                print("API limit reached, aborting")
                break
            continue

        paper = result.paper
        nodes[paper_id] = result

        print(f'[{len(nodes)} / {max_size}] {paper.title} (score {cur_f_score})')

        if len(nodes) >= max_size:
            print("Hit max size threshold")
            break

        neighbor: Paper
        for neighbor in result.references:
            neighbor_id = neighbor.id

            # tentative_gScore is the distance from start to the neighbor through current
            tentative_g_score = g_score.get(paper_id, Infty) + edge_cost(paper, neighbor)
            if tentative_g_score < g_score.get(neighbor_id, Infty):
                # This path to neighbor is better than any previous one. Record it!
                g_score[neighbor_id] = tentative_g_score
                f_score[neighbor_id] = g_score.get(neighbor_id, Infty) + cost(neighbor)
                if is_not_in_open_set(neighbor):
                    push(neighbor_id)

    return Graph(nodes)

