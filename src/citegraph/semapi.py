from typing import Dict, Optional

import requests_cache
import semanticscholar

from citegraph.model import Biblio, PaperAndRefs, PaperId

API_URL = 'http://api.semanticscholar.org/v1'



class PaperDb(object):

    # Cache requests made to semanticscholar, since they are idempotent
    # This is super important! But since the DB is also very badly
    # structured it takes a lot of disk space
    requests_cache.install_cache(cache_name="semapi", backend='sqlite')


    def __init__(self, bibdata: Biblio):
        self.bibdata = bibdata
        self.memcache = {}

    def fetch_from_id(self, paper_id: PaperId) -> Optional[PaperAndRefs]:
        """Returns an entry a"""
        if paper_id in self.memcache:
            return self.memcache[paper_id]

        # print(f"Requesting {paper_id}...", end="")
        paper_dict: Dict = semanticscholar.paper(paper_id)
        # print(f" done.")

        if len(paper_dict.keys()) == 0:
            result = None
        else:
            result = PaperAndRefs(paper=self.bibdata.make_entry(paper_dict),
                                  references=[self.bibdata.make_entry(ref) for ref in paper_dict["references"]],
                                  citations=[self.bibdata.make_entry(ref) for ref in paper_dict["citations"]]
                                  )
            result.id = paper_dict["paperId"]
        self.memcache[paper_id] = result
        return result

