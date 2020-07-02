from typing import NewType, List, Dict

import pybtex.database as bibtex
from pybtex.database.input.bibtex import Parser as BibParser

SEMAPI_ID_FIELD = "semapi_id"
ABSTRACT_FIELD = "_abstract"

Person = bibtex.Person

PaperId = NewType("PaperId", str)


class Paper(object):

    def __init__(self, fields, authors,
                 type_="article",
                 bibtex_id=None):
        self.fields = fields
        self.authors = authors
        self.type_ = type_
        self.id = fields.get(SEMAPI_ID_FIELD, None) or bibtex_id
        self.bibtex_id = bibtex_id


    def __getattr__(self, name):
        return self.fields.get(name, None)


    def __eq__(self, other):
        if not isinstance(other, Paper):
            return super(Paper, self).__eq__(other)
        else:
            return self.id and self.id == other.id or self.title == other.title


    def __hash__(self):
        return hash(self.id) if self.id else hash(self.title)

    def __str__(self):
        return f"{self.year} {self.title}"



class PaperAndRefs(Paper):

    def __init__(self, references, citations, paper):
        super().__init__(fields=paper.fields, authors=paper.authors, type_=paper.type_, bibtex_id=paper.bibtex_id)
        self.references: List[Paper] = references
        self.citations: List[Paper] = citations


    @property
    def paper(self):
        return self


    @property
    def in_degree(self):
        return len(self.citations)


    @property
    def out_degree(self):
        return len(self.references)

    def __hash__(self):
        return hash(id)

    def __eq__(self, other):
        return isinstance(other, Paper) and id == other.id



class Biblio(object):
    """Wrapper around a bib file"""


    def __init__(self, bibdata: bibtex.BibliographyData):
        self.bibdata = bibdata
        self.by_norm_title: Dict[str, Paper] = {
            paper.fields["title"].lower(): Paper(paper.fields, paper.persons["author"],
                                                 # type_=paper,
                                                 bibtex_id=paper.key)
            for paper in bibdata.entries.itervalues()
        }
        self.id_to_bibkey = {}


    def __contains__(self, paper: Paper):
        """
        Returns whether this bib file contains the given entry.
        """
        return paper.id and paper.id in self.id_to_bibkey \
               or paper.bibtex_id and paper.bibtex_id in self.bibdata.entries

    def __iter__(self):
        return iter(self.by_norm_title.values())


    def make_entry(self, paper_dict) -> Paper:
        """
        Retrieve the bib entry corresponding to the given semanticscholar paper result.
        If the paper is present in the bib file, then that entry is returned.
        Otherwise a new entry is created.

        :param paper_dict: Semapi result
        :return: An entry
        """
        paper_id = paper_dict["paperId"]

        bibtex_entry = self.by_norm_title.get(paper_dict["title"].lower(), None)

        if bibtex_entry:  # paper is in bibtex file, prefer data from that file
            # save mapping from ID to bibtex key
            bibtex_entry.id = paper_id
            self.id_to_bibkey[paper_id] = bibtex_entry.bibtex_id
            # print("  Found key %s in bib file" % bibtex_entry.key)
            bibtex_entry.fields[ABSTRACT_FIELD] = paper_dict.get("abstract", "")
            return bibtex_entry
        else:
            fields = {
                "title": paper_dict["title"],
                "year": paper_dict["year"],
                SEMAPI_ID_FIELD: paper_id,
                ABSTRACT_FIELD: paper_dict.get("abstract", ""),
            }

            authors = [bibtex.Person(author["name"]) for author in paper_dict["authors"]]
            return Paper(type_="article", authors=authors, fields=fields)


    @staticmethod
    def from_file(filename) -> 'Biblio':
        return Biblio(BibParser().parse_file(filename))


    @staticmethod
    def empty() -> 'Biblio':
        return Biblio(bibtex.BibliographyData())

