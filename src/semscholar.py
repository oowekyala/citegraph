import semanticscholar
import pybtex.database as bibtex
from pybtex.database import Entry as BibEntry
from typing import NewType, List, Dict

import graphviz as g

import requests_cache, html, textwrap

# Cache requests made to semanticscholar, since they are idempotent
# This is super important!
SEMAPI_ID_FIELD = "semapi_id"
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



class Biblio(object):
    """Wrapper around a bib file"""


    def __init__(self, bibdata: bibtex.BibliographyData):
        self.bibdata = bibdata
        self.by_norm_title: Dict[str, BibEntry] = {
            paper.fields["title"].lower(): paper for paper in bibdata.entries.itervalues()
        }
        self.id_to_bibkey = {}


    def __contains__(self, entry: BibEntry):
        """
        Returns whether this bib file contains the given entry.
        """
        return entry.fields[SEMAPI_ID_FIELD] in self.id_to_bibkey \
            or entry.key in self.bibdata.entries


    def norm_key(self, entry: BibEntry):
        entry.key = self.id_to_bibkey.get(entry.fields[SEMAPI_ID_FIELD], entry.key)

    def make_entry(self, paper_dict) -> BibEntry:
        """
        Retrieve the bib entry corresponding to the given semanticscholar paper result.
        If the paper is present in the bib file, then that entry is returned.
        Otherwise a new entry is created.

        :param paper_dict: Semapi result
        :return: An entry
        """

        bibtex_entry = self.by_norm_title.get(paper_dict["title"].lower(), None)

        paper_id = paper_dict["paperId"]

        if bibtex_entry:  # paper is in bibtex file, prefer data from that file
            # save mapping from ID to bibtex key
            self.id_to_bibkey[paper_id] = bibtex_entry.key
            print("  Found key %s in bib file" % bibtex_entry.key)
            bibtex_entry.fields[SEMAPI_ID_FIELD] = paper_id
            return bibtex_entry
        else:
            fields = {
                "title": paper_dict["title"],
                "year": paper_dict["year"],
                SEMAPI_ID_FIELD: paper_id,
            }

            persons = {
                "author": [bibtex.Person(author["name"]) for author in paper_dict["authors"]]
            }

            entry = BibEntry(type_="article", persons=persons, fields=fields)
            entry.key = paper_id

            return entry

class DotBuilder(object):

    def __init__(self, bibdata: bibtex.BibliographyData, title="Citation graph"):
        self.dot = g.Digraph(title)
        self.bibdata = Biblio(bibdata)

    def get_node_attributes(self, paper_entry: BibEntry):
        attrs = {}

        if paper_entry in self.bibdata:
            attrs["style"] = "filled"

            if paper_entry.fields.get(READ_BIB_KEY, "") == "true":
                attrs["fillcolor"] = "lightblue"
            else:
                attrs["fillcolor"] = "lightyellow"
        else:
            attrs["style"] = "dashed"

        attrs["URL"] = f"https://www.semanticscholar.org/paper/{paper_entry.fields[SEMAPI_ID_FIELD]}"

        return attrs


    def make_label(self, entry: BibEntry):
        fields = entry.fields
        title = fields["title"]
        title = "\n".join(textwrap.wrap(title, width=20))

        first_author: bibtex.Person = next(iter(entry.persons["author"] or []), None) or UNKNOWN_PERSON

        label = "<<B>%s" % html.escape(first_author.last_names[0])
        if "year" in fields:
            label += " (%s)" % fields["year"]

        label += "</B><BR/>" + html.escape(title).replace("\n", "<BR/>") + ">"

        return label


    def add_paper(self, paper_entry: BibEntry):

        self.dot.node(name=paper_entry.key,
                      label=self.make_label(paper_entry),
                      **self.get_node_attributes(paper_entry))


    def get_edge_attributes(self, src: BibEntry, dst: BibEntry):
        attrs = {}

        src_in_bib = src in self.bibdata
        dst_in_bib = dst in self.bibdata
        if src_in_bib ^ dst_in_bib:
            attrs["color"] = "black;0.25:gray" if src_in_bib else "gray;0.75:black"
        elif not src_in_bib or not dst_in_bib:
            attrs["color"] = "gray"
        else:
            attrs["weight"] = "2"

        return attrs


    def cite(self, src_entry: BibEntry, dst_entry: BibEntry):
        self.bibdata.norm_key(src_entry)
        self.bibdata.norm_key(dst_entry)
        self.dot.edge(src_entry.key, dst_entry.key, **self.get_edge_attributes(src_entry, dst_entry))


    def make_entry(self, paper_dict) -> BibEntry:
        return self.bibdata.make_entry(paper_dict)


def build_graph(seeds: List[PaperId], depth: int, dot_builder: DotBuilder):
    """From an initial paper id, crawl its references up to depth.
       A reference is not explored for the next depth if it is not
       contained in the entries (but it's kept in the db).
    """

    done = set([])
    remaining = [] + seeds
    remaining2 = []

    citations = []

    failures = 0
    aborted = False

    while depth > 0 and not aborted:
        depth -= 1
        for paper_id in remaining:
            if paper_id in done:
                continue

            done.add(paper_id)

            paper_dict: Dict = semanticscholar.paper(paper_id)
            if len(paper_dict.keys()) == 0:
                print("Scholar doesn't know paper with id %s" % paper_id)
                failures += 1
                if failures > 10:
                    print("API limit reached, aborting")
                    aborted = True
                    break
                continue

            print("[paper %d] %s" % (len(done), paper_dict["title"]))

            # References are explored up to the given depth even if the paper is not included
            paper_entry = dot_builder.make_entry(paper_dict)
            dot_builder.add_paper(paper_entry)

            for ref in paper_dict["references"]:
                ref_id = ref["paperId"]

                citations.append((paper_entry, dot_builder.make_entry(ref)))
                remaining2.append(ref_id)

        tmp = remaining2
        remaining2 = remaining
        remaining = tmp

    for (src, dst) in citations:
        if dst.fields[SEMAPI_ID_FIELD] in done:
            dot_builder.cite(src, dst)
