import graphviz as g
from typing import NamedTuple
import os, textwrap, html

import pybtex.database as bibtex
from pybtex.database.input.bibtex import Parser as BibParser

# Generate a citation graph from a bibtex bibliography

# Citations need to be filled in manually inside a `_cites` key of each bibtex entry
# If you mention _read={true}, the node changes color

# TODO
#  * custom DOT attributes for eg books
#  * extensible metadata in bibtex -> format options at call time
#      eg '--tag=old->[style=dotted]', then all entries that have a key "old" are dotted

DEFAULT_FORMAT = "pdf"
CITE_BIB_KEY = "_cites"
READ_BIB_KEY = "_read"
UNKNOWN_PERSON = bibtex.Person(string="Unknown von Nowhere")

class Args(NamedTuple):
    dotfile: str
    output_file: str
    renderformat: str
    bibfile: str



def to_dot(bibfile: str) -> g.Digraph:
    bibdata: bibtex.BibliographyData = BibParser().parse_file(bibfile)

    dot = g.Digraph("Citation graph")

    entry: bibtex.Entry
    for entry in bibdata.entries.itervalues():
        (color, style) = ("lightblue", "filled") if entry.fields.get(READ_BIB_KEY, "") == "true" else (None, None)

        dot.node(name=entry.key, label=make_label(entry), style=style, fillcolor=color)  # todo limit size
        refs = entry.fields.get(CITE_BIB_KEY, None)
        if refs:
            for refid in refs.split(','):
                dot.edge(entry.key, refid.strip())

    return dot



def make_label(entry: bibtex.Entry):
    fields = entry.fields
    title = fields["title"]
    title = "\n".join(textwrap.wrap(title, width=20))

    first_author: bibtex.Person = next(iter(entry.persons["author"] or []), None) or UNKNOWN_PERSON

    label = "<<B>%s" % html.escape(first_author.last_names[0])
    if "year" in fields:
        label += " (%s)" % fields["year"]

    label += "</B><BR/>" + html.escape(title).replace("\n", "<BR/>") + ">"

    return label



def parse_args() -> Args:
    from optparse import OptionParser
    parser = OptionParser(usage="usage: %prog [options] file.bib")
    parser.add_option("-f", "--format", help="Render format, one of %s" % g.FORMATS, metavar="FORMAT", default=DEFAULT_FORMAT)
    parser.add_option("-d", "--dotfile", help="Dump for generated DOT (default none)", metavar="FILE")
    parser.add_option("-o", "--outfile", help="Path to the rendered file (default next to bib file)", metavar="FILE")

    (options, args) = parser.parse_args()

    if len(args) == 0:
        parser.error("Missing bibtex file")
    elif len(args) > 1:
        parser.error("Expecting a single positional argument")

    bibfile = args[0]
    render_file = options.outfile or os.path.splitext(bibfile)[0]

    return Args(
        renderformat=options.format,
        bibfile=bibfile,
        dotfile=options.dotfile,
        output_file=render_file
    )


if __name__ == "__main__":
    args = parse_args()
    graph = to_dot(args.bibfile)
    if args.dotfile:
        graph.save(filename=args.dotfile)

    graph.render(filename=args.output_file, format=args.renderformat)
