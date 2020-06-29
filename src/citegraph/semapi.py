import semanticscholar
from typing import NewType, List, Dict, Optional, NamedTuple

import requests_cache

from citegraph.model import Biblio, BibEntry

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



class PaperAndRefs(NamedTuple):
    entry: BibEntry
    references: List[PaperId]



class PaperDb(object):
    # Cache requests made to semanticscholar, since they are idempotent
    # This is super important!
    requests_cache.install_cache(cache_name="semapi", backend='sqlite')


    def __init__(self, bibdata: Biblio):
        self.bibdata = bibdata


    def fetch_from_id(self, paper_id: PaperId) -> Optional[PaperAndRefs]:
        """Returns an entry a"""
        paper_dict: Dict = semanticscholar.paper(paper_id)

        if len(paper_dict.keys()) == 0:
            return None
        else:
            return PaperAndRefs(self.bibdata.make_entry(paper_dict),
                                [ref["paperId"] for ref in paper_dict["references"]])
