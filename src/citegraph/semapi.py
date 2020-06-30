import semanticscholar
from typing import NewType, List, Dict, Optional, NamedTuple

import requests_cache

from citegraph.model import Biblio, Paper

PaperId = NewType("PaperId", str)


class PaperAndRefs(NamedTuple):
    paper: Paper
    references: List[Paper]


class PaperDb(object):
    # Cache requests made to semanticscholar, since they are idempotent
    # This is super important!
    requests_cache.install_cache(cache_name="semapi", backend='sqlite')


    def __init__(self, bibdata: Biblio):
        self.bibdata = bibdata
        self.memcache = {}


    def fetch_or_err(self, paper_id: PaperId):
        result = self.fetch_from_id(paper_id)
        if not result:
            raise AssertionError(f"Id {paper_id} is unknown")
        return result

    # TODO this is embarrassingly parallel

    def fetch_from_id(self, paper_id: PaperId) -> Optional[PaperAndRefs]:
        """Returns an entry a"""
        if paper_id in self.memcache:
            return self.memcache[paper_id]

        paper_dict: Dict = semanticscholar.paper(paper_id)

        if len(paper_dict.keys()) == 0:
            result = None
        else:
            result = PaperAndRefs(paper=self.bibdata.make_entry(paper_dict),
                                  references=[self.bibdata.make_entry(ref) for ref in paper_dict["references"]])
        self.memcache[paper_id] = result
        return result
