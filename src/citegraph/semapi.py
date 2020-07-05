import sqlite3
from typing import Dict, Optional, List, Iterable

import semanticscholar

from citegraph.model import Biblio, PaperAndRefs, PaperId, Person,Paper

API_URL = 'http://api.semanticscholar.org/v1'


def _tupled_sort(iterable: Iterable) -> Iterable:
    """
    Sort an iterable of tuples using the last component as a key,
    returns an iterable of tuples that doesn't include the key.
    """
    lst = sorted(iterable, key=lambda tup: tup[-1])
    it = iter(lst)
    while True:
        elt = next(it)
        yield elt[:-1]

class PaperDb(object):

    """
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

    def __paper_from_db(self, paper_id: PaperId, with_refs: bool):
        c = self.dbconn.cursor()
        c.execute("SELECT title, year FROM Papers WHERE id=?", (paper_id,))
        found = c.fetchone()
        if not found or with_refs and not self.__is_resolved(paper_id):
            return None

        (title, year) = found

        paper = Paper(fields={"title": title, "year": year},
                      id=paper_id,
                      authors=self.__authors_from_db(paper_id))

        if not with_refs:
            return paper

        citations = [self.__paper_from_db(id[0], False)
                     for id in c.execute(f"SELECT src FROM Citations WHERE dst=?", (paper_id,))]
        references = [self.__paper_from_db(id[0], False)
                      for id in c.execute(f"SELECT dst FROM Citations WHERE src=?", (paper_id,))]

        c.close()

        return PaperAndRefs(
            paper=paper,
            citations=citations,
            references=references
        )


    def __is_resolved(self, paper_id: PaperId) -> bool:
        self.cursor.execute("SELECT id FROM Resolved WHERE id=?", (paper_id,))
        return bool(self.cursor.fetchone())


    def __authors_from_db(self, paper_id: PaperId) -> List[Person]:
        return [Person(tup[0]) for tup in _tupled_sort(self.dbconn.execute("SELECT Authors.name, AuthorLinks.rank FROM Authors INNER JOIN AuthorLinks ON AuthorLinks.authorId = Authors.id WHERE AuthorLinks.paperId=?", (paper_id,)))]

    def __update_db(self, response) -> PaperAndRefs:

        authors = {}
        authorship = set([])
        cites = []
        papers = []

        def paper_update(dic):
            papers.append((dic["paperId"], dic["title"] or "", int(dic["year"] or 0)))

        def author_update(dic, paper_id):
            for i, author in enumerate(dic["authors"]):
                author_id = author["authorId"]
                authors[author_id] = author["name"]
                authorship.add((paper_id, author_id, i))

        paper_id = response["paperId"]
        paper_update(response)
        author_update(response, paper_id)

        for ref in response["references"]:
            ref_id = ref["paperId"]
            cites.append((paper_id, ref_id))
            author_update(ref, ref_id)
            paper_update(ref)

        for ref in response["citations"]:
            ref_id = ref["paperId"]
            cites.append((ref_id, paper_id))
            author_update(ref, ref_id)
            paper_update(ref)

        self.cursor.executemany("REPLACE INTO Papers VALUES (?,?,?)", papers)
        self.cursor.executemany("REPLACE INTO Citations VALUES (?,?)", cites)
        self.cursor.executemany("REPLACE INTO Authors VALUES (?,?)", authors.items())
        self.cursor.executemany("REPLACE INTO AuthorLinks VALUES (?,?,?)", authorship)
        # mark this paper as resolved
        self.cursor.execute("REPLACE INTO Resolved VALUES (?, 1)", (paper_id,))

        self.dbconn.commit()

        return self.__paper_from_db(paper_id, True)
        # return PaperAndRefs(paper=self.bibdata.make_entry(response),
        #                     references=[self.bibdata.make_entry(ref) for ref in response["references"]],
        #                     citations=[self.bibdata.make_entry(ref) for ref in response["citations"]]
        #                     )


    def fetch_from_id(self, paper_id: PaperId) -> Optional[PaperAndRefs]:
        """Returns an entry a"""
        if paper_id in self.memcache:
            return self.memcache[paper_id]

        found = self.__paper_from_db(paper_id, True)
        if found:
            return self.bibdata.enrich(found)

        # print(f"Requesting {paper_id}...", end="")
        paper_dict: Dict = semanticscholar.paper(paper_id)
        # print(f" done.")

        if len(paper_dict.keys()) == 0:
            result = None
        else:
            result = self.__update_db(response=paper_dict)
            result.id = paper_dict["paperId"]
            result = self.bibdata.enrich(result)

        self.memcache[paper_id] = result
        return result


    def __enter__(self):
        self.dbconn = sqlite3.connect(self.dbfile)
        self.cursor = self.dbconn.cursor()

        self.cursor.execute("CREATE TABLE IF NOT EXISTS Papers (id VARCHAR PRIMARY KEY, title VARCHAR, year INTEGER);")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS Resolved (id VARCHAR PRIMARY KEY, resolved BOOL,
                                   FOREIGN KEY (id) REFERENCES Papers(id));
        """)
        self.cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS Citations (src VARCHAR, dst VARCHAR, 
                                   FOREIGN KEY (src) REFERENCES Papers(id),
                                   FOREIGN KEY (dst) REFERENCES Papers(id),
                                   CONSTRAINT unique_edge UNIQUE (src, dst));
        """)
        self.cursor.execute("CREATE TABLE IF NOT EXISTS Authors (id INTEGER PRIMARY KEY, name VARCHAR);")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS AuthorLinks (paperId VARCHAR, authorId INTEGER, rank INTEGER,
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
