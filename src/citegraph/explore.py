from typing import List, Dict, Optional, Callable
from queue import PriorityQueue

from citegraph.model import Biblio, Paper, semapi_id
from citegraph.graph import GraphBuilder
from citegraph.semapi import PaperId, PaperDb, PaperAndRefs

# TODO
#  Heuristic graph search


Infty = 2 ** 10_000


def astar(seeds: List[PaperId],
          builder: GraphBuilder,
          max_size: int,
          db: PaperDb):
    """
    Builds the initial graph by fetching reference data from semapi.
    This does some heuristic search to find papers that are the closest
    from the bibliography entries.

    :param seeds: Ids of the papers to start the search with
    :param builder: Graph builder
    :param max_size: Maximum number of nodes
    :param db: API to get references
    :return:
    """

    biblio = builder.bibdata

    def weight(paper: Paper):
        return 5 if paper not in biblio else 2

    def edge_weight(src: Paper, dst: Paper) -> int:
        return 1  # TODO

    open_set = PriorityQueue()

    # For node n, g_score[n] is the cost of the best path from start to n currently known.
    g_score = {id: 0 for id in seeds}

    # For node n, f_score[n] := g_score[n] + h(n). f_score[n] represents our current best guess as to
    # how short a path from start to finish can be if it goes through n.
    f_score = {id: 5 for id in seeds}

    nodes = {}
    edges = []

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
        nodes[paper.key] = paper

        print(f'[{len(nodes)} / {max_size}] {paper.fields["title"]} (score {cur_f_score})')

        if len(nodes) >= max_size:
            print("Hit max size threshold")
            break

        neighbor: Paper
        for neighbor in result.references:
            neighbor_id = semapi_id(neighbor)
            edges.append((paper, neighbor))

            # tentative_gScore is the distance from start to the neighbor through current
            tentative_g_score = g_score.get(paper_id, Infty) + edge_weight(paper, neighbor)
            if tentative_g_score < g_score.get(neighbor_id, Infty):
                # This path to neighbor is better than any previous one. Record it!
                g_score[neighbor_id] = tentative_g_score
                f_score[neighbor_id] = g_score.get(neighbor_id, Infty) + weight(neighbor)
                if is_not_in_open_set(neighbor):
                    push(neighbor_id)

    for paper in nodes.values():
        builder.add_paper(paper)

    for (src, dst) in edges:
        if dst.key in nodes:
            builder.cite(src, dst)



def build_graph(seeds: List[PaperId],
                depth: int,
                builder: GraphBuilder,
                db: PaperDb):
    """
    Build the graph.

    :param seeds: Initial papers to fetch
    :param depth: Maximum depth at which to delve in the graph
    :param builder: Reacts to the addition of nodes & edges
    :param db: Source of paper information
    :return:
    """

    done = set([])
    by_id = {}
    remaining = [] + seeds
    remaining2 = []

    citations: List[(Paper, PaperId)] = []

    failures = 0
    aborted = False

    while depth > 0 and not aborted:
        depth -= 1
        for paper_id in remaining:

            if paper_id in done:
                continue

            done.add(paper_id)

            result: Optional[PaperAndRefs] = db.fetch_from_id(paper_id)

            if not result:
                print("Scholar doesn't know paper with id %s" % paper_id)
                failures += 1
                if failures > 10:
                    print("API limit reached, aborting")
                    aborted = True
                    break
                continue

            paper = result.paper

            by_id[paper_id] = paper

            print("[paper %d] %s" % (len(done), paper.fields["title"]))

            builder.add_paper(paper)

            for ref in result.references:
                citations.append((paper, ref.paperId))
                remaining2.append(ref.paperId)

        tmp = remaining2
        remaining2 = remaining
        remaining = tmp

    for (src, dst) in citations:
        if dst in by_id:
            builder.cite(src, by_id[dst])
