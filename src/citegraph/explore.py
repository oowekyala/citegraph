from typing import List, Dict, Optional,Tuple

from citegraph.model import Biblio, BibEntry
from citegraph.graph import GraphBuilder
from citegraph.semapi import PaperId, PaperDb, PaperAndRefs

# TODO
#  Heuristic graph search


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

    citations: List[(BibEntry, PaperId)] = []

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

            (paper, references) = result

            by_id[paper_id] = paper

            print("[paper %d] %s" % (len(done), paper.fields["title"]))

            builder.add_paper(paper)

            for ref_id in references:
                citations.append((paper, ref_id))
                remaining2.append(ref_id)

        tmp = remaining2
        remaining2 = remaining
        remaining = tmp

    for (src, dst) in citations:
        if dst in by_id:
            builder.cite(src, by_id[dst])
