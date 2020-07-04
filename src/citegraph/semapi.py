import sqlite3
from typing import Dict, Optional, List

import semanticscholar

from citegraph.model import Biblio, PaperAndRefs, PaperId, Person,Paper

API_URL = 'http://api.semanticscholar.org/v1'

class PaperDb(object):
    """
    Database where paper information is stored.

    Tables:

    PAPER
    (id: primary str) * (title: str) * (year: int)

    CITATION
    (src: paperId) * (dst: paperId)

    AUTHOR
    (id: primary str) * (name: str)

    AUTHORSHIP
    (paperId) * (authorId) * (rank: int)

    RESOLVED
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
        c.execute("SELECT title, year FROM Paper WHERE Paper.id=?", (paper_id,))
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
                     for id in c.execute("SELECT src FROM Citation WHERE dst=?", (paper_id,))]
        references = [self.__paper_from_db(id[0], False)
                      for id in c.execute("SELECT dst FROM Citation WHERE src=?", (paper_id,))]

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
        lst = [tup for tup in self.dbconn.execute("SELECT Author.name, Authorship.rank FROM Author INNER JOIN Authorship ON Authorship.authorId = Author.id WHERE Authorship.paperId=?", (paper_id,))]
        lst.sort(key=lambda tup: tup[1])
        return [Person(tup[0]) for tup in lst]

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

        self.cursor.executemany("REPLACE INTO Paper VALUES (?,?,?)", papers)
        self.cursor.executemany("REPLACE INTO Citation VALUES (?,?)", cites)
        self.cursor.executemany("REPLACE INTO Author VALUES (?,?)", authors.items())
        self.cursor.executemany("REPLACE INTO Authorship VALUES (?,?,?)", authorship)
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

        self.cursor.execute("CREATE TABLE IF NOT EXISTS Paper (id VARCHAR PRIMARY KEY, title VARCHAR, year INT);")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS Resolved (id VARCHAR PRIMARY KEY, resolved BOOL);")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS Citation (src VARCHAR, dst VARCHAR, 
                                   CONSTRAINT unique_edge UNIQUE (src, dst));
        """)
        self.cursor.execute(" CREATE TABLE IF NOT EXISTS Author (id VARCHAR PRIMARY KEY, name VARCHAR);")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS Authorship (paperId VARCHAR, authorId VARCHAR, rank INT,
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
