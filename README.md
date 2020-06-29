# Citegraph

Generate a citation graph from a Bibtex bibliography, discover
new articles.


This uses the semanticscholar API to fetch references for articles.


Principle:
* Find the IDs of the roots of your graph
* Launch the program, which will perform a graph exploration 
starting from those roots. The exploration uses your Bibtex 
file to find the most relevant articles to explore next


### Customizing graph appearance

TODO

You can customize the rendering for specific papers by annotating
the corresponding bibtex entry with some attributes.

Then you define a mapping from those custom attributes to DOT
attributes (styling attributes, etc)


For example, say there are some articles in your bibliography
that you've not read yet, and you want to distinguish them visually.

Add a field to those entries in your `.bib` file, eg `is_read={false}`.

Then, in your citegraph.yaml, define how this attribute is interpreted:
```yaml
attrs:
  is_read:
    false:


```






