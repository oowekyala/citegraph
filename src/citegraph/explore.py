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


Infty = 2 ** 1000


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
    api_weight: float
    beta: float
    distance_penalty: float
    diffusion_factor: float
    """
    The parameter δ (0 ≤ δ < 1) determines the diffusion factor, where values closer to 1 increase 
    the diffusion.
    """

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

    params = Params(api_weight=2, beta=1, distance_penalty=-2, diffusion_factor=0.5)

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


    citations = {}  # predecessors
    references = {} # successors

    def add_ref(src, dst):
        """Record that paper src cites paper dst."""
        if dst in citations:
            citations[dst.id].add(src.id)
        else:
            citations[dst.id] = {src.id}

        if src in references:
            references[src.id].add(dst.id)
        else:
            references[src.id] = {dst.id}


    def api(p: Paper) -> float:
        """a-priori interest in the paper"""
        if p.id == 'bdc3d618db015b2f17cd76224a942bfdfc36dc73':
            # https://www.semanticscholar.org/paper/Intravenous-Oxycodone-Versus-Other-Intravenous-for-Raff-Belbachir/bdc3d618db015b2f17cd76224a942bfdfc36dc73
            # Buggy article (224K citations)
            return 0

        # TODO topicalness * influence

        base = len(graph_nodes.keys() & citations.get(p.id, set())) + \
               len(graph_nodes.keys() & references.get(p.id, set()))

        # if p.paper.year:
        #     citations_per_year = p.in_degree / (1 + 2020 - int(p.paper.year))
        #     base = citations_per_year
        # else:
        #     base = p.in_degree / (1 + p.out_degree)

        return base * 3 if p in biblio else base


    def cost(paper: Paper):
        return 1


    def distance_from_focal(p: Paper):
        return g_score.get(p.id, 10)


    def degree_of_interest(p: Paper) -> float:
        return params.api_weight * api(p) \
               + params.distance_penalty * distance_from_focal(p)

    # fetch the roots
    roots = db.batch_fetch(seeds, exhandler=exception_handler)

    # For node n, g_score[n] is the cost of the best path from start to n currently known.
    g_score = {p.id: 0 for p in roots}
    nodes = {p.id: p for p in roots}
    graph_nodes = {}

    while True:
        (best, cur_doi) = max([(n, degree_of_interest(n)) for n in nodes.values() if n.id not in graph_nodes],
                              key=lambda t: t[1],
                              default=(None, 0))
        if not best:
            break  # no more nodes

        if best.id in graph_nodes:
            continue

        pre_id = best.id
        result: Optional[PaperAndRefs] = db.fetch_from_id(best.id)

        if not result:
            print("Scholar doesn't know paper with id %s" % best.id)
            request_failures += 1
            # todo cleanup reference count?
            if request_failures > FAILURE_LIMIT:
                print("API limit reached, aborting")
                break
            continue

        best = result
        graph_nodes[best.id] = best
        if pre_id != best.id:
            del nodes[pre_id]
            # citations[best.id] = citations[pre_id]
            # del citations[pre_id]
            # references[best.id] = references[pre_id]
            # del references[pre_id]

        print(f'[{len(graph_nodes)} / {max_size} / {len(nodes)}] (DOI {cur_doi}) {best.title} ')
        if len(graph_nodes) >= max_size:
            print("Hit max size threshold")
            break

        for citing in best.citations:
            nodes[citing.id] = citing
            add_ref(citing, best)

        for cited in best.references:
            nodes[cited.id] = cited
            add_ref(best, cited)

            # tentative_gScore is the distance from start to the neighbor through current
            tentative_g_score = g_score.get(best.id, Infty) + cost(cited) + edge_disinterest(best, cited)
            cur_g_score = g_score.get(cited.id, Infty)
            best_g_score = min(tentative_g_score, cur_g_score)
            if cur_g_score != best_g_score:
                g_score[cited.id] = best_g_score

    return Graph(graph_nodes)
