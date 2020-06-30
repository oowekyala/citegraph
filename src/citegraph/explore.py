from typing import List, Dict, Optional, Callable
from queue import PriorityQueue

from citegraph.model import Biblio, Paper, semapi_id
from citegraph.draw import GraphRenderer
from citegraph.semapi import PaperId, PaperDb, PaperAndRefs



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
                    if semapi_id(ref) in self.nodes:
                        builder.add_edge(paper.paper, ref)



Infty = 2 ** 10_000



def author_similarity(p1: Paper, p2: Paper) -> int:
    total_authors = len(p1.persons["author"]) + len(p2.persons["author"])
    authors_in_common = len(author_set(p1) & author_set(p2))
    return authors_in_common



def author_set(p1):
    return {" ".join(p.last_names) for p in p1.persons["author"]}



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
        return base - min(author_similarity(src, dst), 3)


    open_set = PriorityQueue()

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
        id = semapi_id(p)
        for (_, c) in open_set.queue:
            if c == id:
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

        print(f'[{len(nodes)} / {max_size}] {paper.fields["title"]} (score {cur_f_score})')

        if len(nodes) >= max_size:
            print("Hit max size threshold")
            break

        neighbor: Paper
        for neighbor in result.references:
            neighbor_id = semapi_id(neighbor)

            # tentative_gScore is the distance from start to the neighbor through current
            tentative_g_score = g_score.get(paper_id, Infty) + edge_cost(paper, neighbor)
            if tentative_g_score < g_score.get(neighbor_id, Infty):
                # This path to neighbor is better than any previous one. Record it!
                g_score[neighbor_id] = tentative_g_score
                f_score[neighbor_id] = g_score.get(neighbor_id, Infty) + cost(neighbor)
                if is_not_in_open_set(neighbor):
                    push(neighbor_id)

    return Graph(nodes)
