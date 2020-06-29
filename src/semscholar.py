import semanticscholar
import pybtex.database as bibtex
from typing import NewType, List, Dict, Iterable

import graphviz as g

import requests_cache, html, textwrap

# Cache requests made to semanticscholar, since they are idempotent
# This is super important!
requests_cache.install_cache(cache_name="semapi", backend='sqlite')

PaperId = NewType("PaperId", str)
"""Accessible Paper Identifiers and Examples:

    S2 Paper ID : 0796f6cd7f0403a854d67d525e9b32af3b277331
    DOI         : 10.1038/nrn3241
    ArXiv ID    : arXiv:1705.10311
    MAG ID      : MAG:112218234
    ACL ID      : ACL:W12-3903
    PubMed ID   : PMID:19872477
    Corpus ID   : CorpusID:37220927
"""

READ_BIB_KEY = "_read"
UNKNOWN_PERSON = bibtex.Person(string="Unknown von Nowhere")


class DotBuilder(object):

    def __init__(self, title="Citation graph"):
        self.dot = g.Digraph(title)


    def add_paper(self, paper_dict, paper_entry: bibtex.Entry):
        (color, style) = ("lightblue", "filled") if paper_entry.fields.get(READ_BIB_KEY, "") == "true" else (None, None)

        self.dot.node(name=paper_entry.key, label=self.make_label(paper_entry), style=style, fillcolor=color)


    def make_label(self, entry: bibtex.Entry):
        fields = entry.fields
        title = fields["title"]
        title = "\n".join(textwrap.wrap(title, width=20))

        first_author: bibtex.Person = next(iter(entry.persons["author"] or []), None) or UNKNOWN_PERSON

        label = "<<B>%s" % html.escape(first_author.last_names[0])
        if "year" in fields:
            label += " (%s)" % fields["year"]

        label += "</B><BR/>" + html.escape(title).replace("\n", "<BR/>") + ">"

        return label


    def cite(self, src_id, src_entry: bibtex.Entry, dst_id, dst_entry: bibtex.Entry):
        self.dot.edge(src_entry.key, dst_entry.key)



def build_graph(seeds: List[PaperId], depth: int, bibdata: bibtex.BibliographyData, dot_builder: DotBuilder):
    """From an initial paper id, crawl its references up to depth.
       A reference is not explored for the next depth if it is not
       contained in the entries (but it's kept in the db).
    """

    def include(titled):
        return [e for e in bibdata.entries.itervalues()
                if e.fields["title"].lower() == titled["title"].lower()]


    done = set([])
    remaining = [] + seeds
    remaining2 = []

    while depth > 0 and len(remaining) > 0:
        depth -= 1
        for paper_id in remaining.copy():
            if paper_id in done:
                continue

            done.add(paper_id)

            paper: Dict = semanticscholar.paper(paper_id)
            if len(paper.keys()) == 0:
                print("Scholar doesn't know paper with id %s" % paper_id)
                continue

            print("[paper] %s" + paper["title"])

            if include(paper):
                print(" -> included")
                # References are explored up to the given depth even if the paper is not included
                dot_builder.add_paper(paper, include(paper)[0])

            for ref in paper["references"]:
                ref_id = ref["paperId"]

                if include(paper) and include(ref):
                    dot_builder.cite(paper_id, include(paper)[0], ref_id, include(ref)[0])
                    remaining2.append(ref_id)

        tmp = remaining2
        remaining2 = remaining
        remaining = tmp
