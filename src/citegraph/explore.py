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
    distance_penalty: float

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

    params = Params(api_weight=3, distance_penalty=-2)

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
    references = {}  # successors

    def update_multimap(map, k, v):
        if k in map:
            map[k].add(v)
        else:
            map[k] = {v}

    def add_ref(src, dst):
        """Record that paper src cites paper dst."""
        update_multimap(citations, dst.id, src.id)
        update_multimap(references, src.id, dst.id)


    def api(p: Paper) -> float:
        """a-priori interest in the paper"""
        if p.id == 'bdc3d618db015b2f17cd76224a942bfdfc36dc73':
            # https://www.semanticscholar.org/paper/Intravenous-Oxycodone-Versus-Other-Intravenous-for-Raff-Belbachir/bdc3d618db015b2f17cd76224a942bfdfc36dc73
            # Buggy article (224K citations)
            return 0

        # TODO topicalness * influence

        # TODO discount very influential papers
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
