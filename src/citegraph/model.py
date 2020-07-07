import re
from typing import NewType, List, Dict, NamedTuple

import pybtex.database as bibtex
from pybtex.database.input.bibtex import Parser as BibParser

SEMAPI_ID_FIELD = "semapi_id"
ABSTRACT_FIELD = "_abstract"

Person = bibtex.Person

PaperId = NewType("PaperId", str)


class Paper(object):

    def __init__(self,
                 fields: Dict,
                 authors: List[Person],
                 id: PaperId,
                 type_="article",
                 bibtex_id=None):
        self.fields = fields
        self.authors = authors
        self.type_ = type_
        self.id = id or bibtex_id
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


class Citation(NamedTuple):
    paper: Paper
    is_influential: bool


class PaperAndRefs(Paper):

    def __init__(self, references, citations, paper):
        super().__init__(fields=paper.fields, authors=paper.authors,
                         id=paper.id, type_=paper.type_,
                         bibtex_id=paper.bibtex_id)
        self.references: List[Citation] = references
        self.citations: List[Citation] = citations


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
            self._normalize_title(paper.fields["title"])
            : Paper(paper.fields,
                    paper.persons["author"],
                    id=paper.key,
                    bibtex_id=paper.key)
            for paper in bibdata.entries.itervalues()
        }
        self.id_to_bibkey = {}


    @staticmethod
    def _normalize_title(title: str):
        title = title.lower()
        title = re.sub("\\s*[-:]\\s*", "", title)  # delete some punctuation
        title = re.sub("\\s{2,}", " ", title)  # normalize whitespace
        return title


    def __contains__(self, paper: Paper):
        """
        Returns whether this bib file contains the given entry.
        """
        return paper.id and paper.id in self.id_to_bibkey \
               or paper.bibtex_id and paper.bibtex_id in self.bibdata.entries


    def __iter__(self):
        return iter(self.by_norm_title.values())


    def enrich(self, paper):
        bibtex_entry = self.by_norm_title.get(self._normalize_title(paper.title), None)
        if bibtex_entry:
            paper.bibtex_id = bibtex_entry.bibtex_id
            self.id_to_bibkey[paper.id] = bibtex_entry.bibtex_id
        return paper


    @staticmethod
    def from_file(filename) -> 'Biblio':
        return Biblio(BibParser().parse_file(filename))


    @staticmethod
    def empty() -> 'Biblio':
        return Biblio(bibtex.BibliographyData())
