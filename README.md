# Citegraph


Generates easily readable citation graphs. This uses the contents
of a bibtex file to determine what you're interested in.

This uses the semanticscholar API to fetch references for articles.

Requires Python 3.6+

TODO visuals

### Customizing graph appearance


You can specify how individual nodes are styled with a yaml file.
For example:
```yaml
tags:
    read: # an identifier for the tag
        attrs: # DOT attributes:     https://graphviz.gitlab.io/doc/info/attrs.html
            style: bold
        members: # enumerate explicit members using keys of the bibtex file
            - someBibKey
            - another
    
    knuth_articles: # another tag
        attrs: 
            style: filled
            fillcolor: lightyellow
        
        # Select using an arbitrary python expression
        # The bibtex entry is in scope as 'paper'
        selector: 'any("Knuth" in author.last_names for author in paper.authors)'
```
