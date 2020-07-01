from typing import NewType, List, Dict, Optional, NamedTuple, Iterable

import grequests
import semanticscholar

import requests_cache
import concurrent.futures as futures

from citegraph.model import Biblio, Paper

PaperId = NewType("PaperId", str)

API_URL = 'http://api.semanticscholar.org/v1'



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


class PaperDb(object):
    # Cache requests made to semanticscholar, since they are idempotent
    # This is super important!
    requests_cache.install_cache(cache_name="semapi", backend='sqlite')


    def __init__(self, bibdata: Biblio):
        self.bibdata = bibdata
        self.memcache = {}

    def batch_fetch(self, ids: Iterable[PaperId], exhandler) -> List[PaperAndRefs]:
        # TODO parallelize
        res = []
        for id in set(ids):
            r = self.fetch_from_id(id)
            if r:
                res.append(r)
            else:
                exhandler(id, None)
        return res

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


    @staticmethod
    def __get_data(method, id, include_unknown_references=False) -> futures.Future:

        '''Get data from Semantic Scholar API

        :param method: 'paper' or 'author'.
        :param id: :class:`str`.
        :returns: data or empty :class:`dict` if not found.
        :rtype: :class:`dict`
        '''

        method_types = ['paper', 'author']
        if method not in method_types:
            raise ValueError('Invalid method type. Expected one of: {}'.format(method_types))

        url = '{}/{}/{}'.format(API_URL, method, id)
        if include_unknown_references:
            url += '?include_unknown_references=true'
        return grequests.get(url)

        #
        # if r.status_code == 200:
        #     data = r.json()
        #     if len(data) == 1 and 'error' in data:
        #         data = {}
        # elif r.status_code == 429:
        #     raise ConnectionRefusedError('HTTP status 429 Too Many Requests.')
        #
        # return data
