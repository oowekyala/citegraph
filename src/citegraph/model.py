import pybtex.database as bibtex
from typing import NewType, List, Dict
from pybtex.database.input.bibtex import Parser as BibParser

SEMAPI_ID_FIELD = "semapi_id"
ABSTRACT_FIELD = "_abstract"

Paper = bibtex.Entry
Person = bibtex.Person


def semapi_id(e: Paper):
    return e.fields[SEMAPI_ID_FIELD]


class Biblio(object):
    """Wrapper around a bib file"""


    def __init__(self, bibdata: bibtex.BibliographyData):
        self.bibdata = bibdata
        self.by_norm_title: Dict[str, Paper] = {
            paper.fields["title"].lower(): paper for paper in bibdata.entries.itervalues()
        }
        self.id_to_bibkey = {}


    def __contains__(self, entry: Paper):
        """
        Returns whether this bib file contains the given entry.
        """
        return semapi_id(entry) in self.id_to_bibkey \
               or entry.key in self.bibdata.entries


    def norm_key(self, entry: Paper):
        entry.key = self.id_to_bibkey.get(entry.fields[SEMAPI_ID_FIELD], entry.key)


    def make_entry(self, paper_dict) -> Paper:
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
            # print("  Found key %s in bib file" % bibtex_entry.key)
            bibtex_entry.fields[SEMAPI_ID_FIELD] = paper_id
            bibtex_entry.fields[ABSTRACT_FIELD] = paper_dict.get("abstract", "")
            return bibtex_entry
        else:
            fields = {
                "title": paper_dict["title"],
                "year": paper_dict["year"],
                SEMAPI_ID_FIELD: paper_id,
                ABSTRACT_FIELD: paper_dict.get("abstract", "")
            }

            persons = {
                "author": [bibtex.Person(author["name"]) for author in paper_dict["authors"]]
            }

            entry = Paper(type_="article", persons=persons, fields=fields)
            entry.key = paper_id

            return entry

    @staticmethod
    def from_file(filename) -> 'Biblio':
        return Biblio(BibParser().parse_file(filename))

