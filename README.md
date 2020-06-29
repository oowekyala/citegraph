# Citegraph

Generate a citation graph from a Bibtex bibliography, discover
new articles.

This uses the semanticscholar API to fetch references for articles.

Usage
* Find the IDs of the roots of your graph

* Launch the program, which will perform a graph exploration 
starting from those roots. The exploration uses your Bibtex 
file to find the most relevant articles to explore next

### Graph exploration

TODO currently simple BFS from a set of roots

Would be better to use heuristics for relevance of papers,
and explore interesting papers first within the api limit

In principle, we could associate a "cost" to each paper
- Articles in the bibtex file are low-cost by default, but cost may be user-defined (see next section)
- Books are higher cost (longer to read?)
- Cost decreases when the paper has a lot in common with papers that are also low cost (eg same authors)
- Cost increases with distance from the center of the graph

We could then do a heuristic-guided search (A*-like), selecting the least cost paper first. Stop when the graph is too big, or the API limit is reached


### Customizing graph appearance

TODO currently ad-hoc

Ideally, input a yaml file that contains additional tags for
each paper, and some styling information for that 


