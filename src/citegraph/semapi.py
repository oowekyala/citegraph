import sqlite3
from typing import Dict, Optional, List, Iterable

from semanticscholar import SemanticScholar as ScholarApi
from semanticscholar.Paper import Paper as ApiPaper
import requests.exceptions

from .model import *

API_URL = 'http://api.semanticscholar.org/v1'


def _tupled_sort(iterable: Iterable) -> Iterable:
    """
    Sort an iterable of tuples using the last component as a key,
    returns an iterable of tuples that doesn't include the key.
    """
    lst = sorted(iterable, key=lambda tup: tup[-1])
    return (elt[:-1] for elt in lst)


class PaperDb(object):
    """
    Interface to semanticscholar.org. Requests are persisted, because
    the API rate limit is very low.

    Tables:

    Papers
    (id: primary str) * (title: str) * (year: int)

    Citations
    (src: paperId) * (dst: paperId)

    Authors
    (id: primary str) * (name: str)

    AuthorLinks
    (paperId) * (authorId) * (rank: int)

    Resolved
    (id: paperId) * (resolved: bool)


    Resolved stores whether the paper has been downloaded,
    in which case we have all the info about its neighbors.

    """

    def __init__(self, bibdata: Biblio, dbfile: str):
        self.bibdata = bibdata
        self.dbfile = dbfile
        self.dbconn = None
        self.memcache = {}
        self.idcache: Dict[str, int] = {}  # external -> internal id
        self.api = ScholarApi()

    def __paper_from_db(self, internal_id: int, with_refs: bool) -> PaperAndRefs:
        c = self.dbconn.cursor()
        c.execute("SELECT title, year, originalId FROM Papers WHERE id=?", (internal_id,))
        found = c.fetchone()
        if not found or with_refs and not self.__is_resolved(internal_id):
            return None

        (title, year, paper_id) = found

        paper = Paper(fields={"title": title, "year": year},
                      id=paper_id,
                      authors=self.__authors_from_db(internal_id))

        if not with_refs:
            return self.bibdata.enrich(paper)

        citations = [Citation(self.__paper_from_db(id[0], False), bool(id[1]))
                     for id in c.execute(f"SELECT src, influential FROM Citations WHERE dst=?",
                                         (internal_id,))]
        references = [Citation(self.__paper_from_db(id[0], False), bool(id[1]))
                      for id in c.execute(f"SELECT dst, influential FROM Citations WHERE src=?",
                                          (internal_id,))]

        c.close()

        return self.bibdata.enrich(PaperAndRefs(
            paper=paper,
            citations=citations,
            references=references
        ))

    def __paper_from_db_wrapper(self, paper_id: PaperId, with_refs: bool):
        if len(paper_id) != 40:
            return None
        return self.__paper_from_db(internal_id=self._internalize_id(paper_id), with_refs=with_refs)

    def __is_resolved(self, internal_id: int) -> bool:
        self.cursor.execute("SELECT id FROM Resolved WHERE id=?", (internal_id,))
        return bool(self.cursor.fetchone())

    def __authors_from_db(self, internal_id: int) -> List[Person]:
        return [Person(tup[0]) for tup in _tupled_sort(self.dbconn.execute(
            "SELECT Authors.name, AuthorLinks.rank FROM Authors INNER JOIN AuthorLinks ON AuthorLinks.authorId = Authors.id WHERE AuthorLinks.paperId=?",
            (internal_id,)))]

    def __update_db(self, response: ApiPaper) -> PaperAndRefs:

        authors = {}
        authorship = set([])
        cites = []
        papers = []

        # todo handle missing authorId

        def paper_update(paper: ApiPaper):
            id_ = paper.paperId
            papers.append(
                (self._internalize_id(id_), id_, paper.title or "", int(paper.year or 0)))

        def author_update(paper: ApiPaper, paper_id):
            for i, author in enumerate(paper["authors"]):
                author_id = author["authorId"]
                authors[author_id] = author["name"]
                authorship.add((paper_id, author_id, i))

        internal_id = self._internalize_id(response.paperId)
        paper_update(response)
        author_update(response, internal_id)

        def cite_update(papers: List[ApiPaper], is_references):
            for ref in papers:
                if not ref.paperId:
                    continue
                ref_id = self._internalize_id(ref.paperId)
                is_influential = ref.influentialCitationCount > 1  # todo fix that, used to be a field "is_influential"
                if is_references:
                    cites.append((internal_id, ref_id, is_influential))
                else:
                    cites.append((ref_id, internal_id, is_influential))
                author_update(ref, ref_id)
                paper_update(ref)

        cite_update(response.references, True)
        cite_update(response.citations, False)

        self.cursor.executemany("REPLACE INTO Papers VALUES (?,?,?,?)", papers)
        self.cursor.executemany("REPLACE INTO Citations VALUES (?,?,?)", cites)
        self.cursor.executemany("REPLACE INTO Authors VALUES (?,?)", authors.items())
        self.cursor.executemany("REPLACE INTO AuthorLinks VALUES (?,?,?)", authorship)
        # mark this paper as resolved
        self.cursor.execute("REPLACE INTO Resolved VALUES (?, 1)", (internal_id,))

        self.dbconn.commit()

        return self.__paper_from_db(internal_id, True)
        # return PaperAndRefs(paper=self.bibdata.make_entry(response),
        #                     references=[self.bibdata.make_entry(ref) for ref in response["references"]],
        #                     citations=[self.bibdata.make_entry(ref) for ref in response["citations"]]
        #                     )

    def fetch_from_id(self, paper_id: PaperId) -> Optional[PaperAndRefs]:
        """Returns an entry a"""
        if paper_id in self.memcache:
            return self.memcache[paper_id]

        found = self.__paper_from_db_wrapper(paper_id, True)
        if found:
            return found

        try:
            paper: ApiPaper = self.api.get_paper(paper_id)
            error = len(paper.keys()) == 0
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] {str(e)}")
            error = True

        if error:
            result = None
        else:
            result = self.__update_db(response=paper)
            result.id = PaperId(paper.paperId)
            result = result

        self.memcache[paper_id] = result
        return result

    def _internalize_id(self, id: str) -> int:
        # Turn a 40 digit hex ID (160 bits) into a 32 bit int
        # This is a big deal to make the DB smaller
        # todo there's no collision detection
        assert len(id) == 40, "Expect 40 digit ID"

        if id in self.idcache:
            return self.idcache[id]

        def chunk(a, b):
            return int(id[a:b], 16)

        # the id (40 hex digits) can be divided into 5 chunks of 8
        # hex digits, ie 32 bits each
        result = chunk(0, 8) ^ chunk(8, 16) ^ chunk(16, 24) ^ chunk(24, 32) ^ chunk(32, 40)

        self.idcache[id] = result
        return result

    def __enter__(self):
        self.dbconn = sqlite3.connect(self.dbfile)
        self.cursor = self.dbconn.cursor()

        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS Papers (id INTEGER PRIMARY KEY, originalId VARCHAR, title VARCHAR, year INTEGER);")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS Resolved (id INTEGER PRIMARY KEY, resolved BOOL,
                                   FOREIGN KEY (id) REFERENCES Papers(id));
        """)
        self.cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS Citations (src INTEGER NOT NULL, dst INTEGER NOT NULL, influential BOOL NOT NULL,
                                   FOREIGN KEY (src) REFERENCES Papers(id),
                                   FOREIGN KEY (dst) REFERENCES Papers(id),
                                   PRIMARY KEY (src, dst));
        """)
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS Authors (id INTEGER PRIMARY KEY, name VARCHAR);")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS AuthorLinks (paperId INTEGER, authorId INTEGER, rank INTEGER,
                                   FOREIGN KEY (paperId) REFERENCES Papers(id),
                                   FOREIGN KEY (authorId) REFERENCES Authors(id),
                                   CONSTRAINT unique_auth UNIQUE (paperId, authorId));
        """)

        self.dbconn.commit()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dbconn.commit()
        self.dbconn.close()
        if exc_val:
            raise exc_val
        return self
