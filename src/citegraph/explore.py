from typing import List, Dict, Optional, Iterable, NamedTuple
from queue import PriorityQueue

from citegraph.model import Biblio, Paper
from citegraph.draw import GraphRenderer
from citegraph.semapi import PaperId, PaperDb, PaperAndRefs

import concurrent.futures as futures

class Graph(object):

    def __init__(self, nodes: Dict[PaperId, PaperAndRefs]):
        self.nodes = nodes


    def draw(self, builder: GraphRenderer):
        added = set([])
        for paper in self.nodes.values():
            title = paper.paper.fields["title"]
            if title not in added:
                added.add(title)
                builder.add_node(paper.paper)
                for ref in paper.references:
                    if ref.id in self.nodes:
                        builder.add_edge(paper.paper, ref)



Infty = 2 ** 10_000



def authors_in_common(p1: Paper, p2: Paper) -> int:
    return len(author_set(p1) & author_set(p2))



def authors_similarity(p1: Paper, p2: Paper) -> float:
    return authors_in_common(p1, p2) / min(len(p1.authors), len(p2.authors))



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



class Params(NamedTuple):
    api_weight: float
    beta: float
    distance_penalty: float
    diffusion_factor: float
    """
    The parameter δ (0 ≤ δ < 1) determines the diffusion factor, where values closer to 1 increase 
    the diffusion.
    """



class ScoreQueue(object):

    def __init__(self, nodes):
        self.q = PriorityQueue()
        self.nodes = nodes


    def push(self, p: PaperAndRefs, score: float, add_to_nodes=True):
        if add_to_nodes:
            self.nodes[p.id] = p
        self.q.put((-score, p.id))
        return p


    def push_many(self, ps: Iterable[PaperAndRefs], score_fun):
        for p in ps:
            self.nodes[p.id] = p

        for p in ps:
            self.push(p, score=score_fun(p), add_to_nodes=False)
        return ps


    def pop(self):
        (score, id) = self.q.get()
        return -score, self.nodes[id]


    def recompute(self, new_items: List[PaperAndRefs], score_fun):
        lst = set(new_items)
        while self.q.qsize() > 0:
            (_, item) = self.pop()
            lst.add(item)
        self.push_many(lst, score_fun)


    @property
    def is_empty(self) -> bool:
        return self.q.qsize() == 0



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

    params = Params(api_weight=2, beta=1, distance_penalty=-1.5, diffusion_factor=0.5)

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


    def api(p: PaperAndRefs):
        """a-priori interest in the paper"""
        if p.id == 'bdc3d618db015b2f17cd76224a942bfdfc36dc73':
            # https://www.semanticscholar.org/paper/Intravenous-Oxycodone-Versus-Other-Intravenous-for-Raff-Belbachir/bdc3d618db015b2f17cd76224a942bfdfc36dc73
            # Buggy article (224K citations)
            return 0

        # TODO topicalness * influence

        base = 2
        # if p.paper.year:
        #     citations_per_year = p.in_degree / (1 + 2020 - int(p.paper.year))
        #     base = citations_per_year
        # else:
        #     base = p.in_degree / (1 + p.out_degree)

        return base * 3 if p.paper in biblio else base


    def edge_disinterest(src: PaperAndRefs, dst: PaperAndRefs) -> float:
        """ > 0"""
        max_disinterest = 5
        return 1 + max_disinterest * (1 - authors_similarity(src.paper, dst.paper))


    # This caches already computed values to stabilize the api diff, also it avoids
    # infinite recursion on cycles
    api_diff_cache = {}

    def api_diff(p: PaperAndRefs) -> float:
        """Differential a-priori interest. Takes into account the interest values of the
        (as of yet known) neighbors of the paper.
        """
        if p.id in api_diff_cache:
            return api_diff_cache[p.id]

        p_api = api(p)
        api_diff_cache[p.id] = p_api
        # todo better concept of "topicalness"
        #   nodes that are in the graph should be better weighted
        #   irrelevant neighbors should be penalized
        neighbor_interest = max((api_diff(nodes[ref.id]) / edge_disinterest(p, nodes[ref.id])
                                 for ref in [*p.references, *p.citations] if ref.id in nodes),
                                default=0)

        new_val = max(p_api, params.diffusion_factor * neighbor_interest)
        api_diff_cache[p.id] = new_val
        return new_val


    def cost(paper: PaperAndRefs):
        return 1


    def distance_from_focal(p: PaperAndRefs):
        return g_score.get(p.id, 10)


    def degree_of_interest(p: PaperAndRefs) -> float:
        # α⋅APIdiff(x) + β⋅UIdiff(x,z) + γ⋅D(x,y)
        # todo user interest
        return params.api_weight * api_diff(p) \
               + params.beta * 0 \
               + params.distance_penalty * distance_from_focal(p)


    def is_done():
        return queue.is_empty or request_failures > FAILURE_LIMIT


    nodes: Dict[PaperId, PaperAndRefs] = {}

    queue = ScoreQueue(nodes)

    graph_nodes = {}

    # push the roots
    roots = db.batch_fetch(seeds, exhandler=exception_handler)

    # For node n, g_score[n] is the cost of the best path from start to n currently known.
    g_score = {p.id: 0 for p in roots}

    # For node n, f_score[n] := g_score[n] + h(n). f_score[n] represents our current best guess as to
    # how short a path from start to finish can be if it goes through n.
    f_score = {p.id: 1 for p in roots}

    # todo roots should probably be added to the graph eagerly,
    #  and their connections figured out as initialization state
    queue.push_many(roots, score_fun=degree_of_interest)

    while not is_done():
        (cur_doi, best) = queue.pop()

        if best.id in graph_nodes:
            continue

        graph_nodes[best.id] = best

        print(f'[{len(graph_nodes)} / {max_size} / {len(nodes)}] (DOI {cur_doi}) {best.paper.title} ')
        if len(graph_nodes) >= max_size:
            print("Hit max size threshold")
            break

        neighbors = db.batch_fetch([p.id for p in best.references], exhandler=exception_handler)

        # This part is specific to the distance calculation
        # FIXME this doesn't explore everyone
        for neighbor in neighbors:
            neighbor_id = neighbor.id

            # tentative_gScore is the distance from start to the neighbor through current
            tentative_g_score = g_score.get(best.id, Infty) + edge_disinterest(best, neighbor)
            cur_g_score = g_score.get(neighbor_id, Infty)
            best_g_score = min(tentative_g_score, cur_g_score)
            if cur_g_score != best_g_score:
                g_score[neighbor_id] = best_g_score
                f_score[neighbor_id] = best_g_score + cost(neighbor)

        api_diff_cache = {}
        queue.recompute(neighbors, score_fun=degree_of_interest)

    return Graph(graph_nodes)
