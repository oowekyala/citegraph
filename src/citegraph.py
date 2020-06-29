import graphviz as g
import bibtexparser as btex
from bibtexparser.bibdatabase import BibDatabase
from typing import NamedTuple
import os, textwrap, html

DEFAULT_FORMAT = "pdf"



class Args(NamedTuple):
    dotfile: str
    output_file: str
    renderformat: str
    bibfile: str



def to_dot(bibfile: str) -> g.Digraph:
    with open(bibfile, "r") as infile:
        bibdata: BibDatabase = btex.load(infile)

    dot = g.Digraph("Citation graph")

    for entry in bibdata.entries:
        pubid = entry["ID"]

        (color, style) = ("lightblue", "filled") if entry.get("_read", "") == "true" else (None, None)

        dot.node(name=pubid, label=make_label(entry), style=style, fillcolor=color)  # todo limit size
        refs = entry.get("_cites", None)
        if refs:
            for refid in refs.split(','):
                dot.edge(pubid, refid.strip())

    return dot



def make_label(entry):
    title = entry["title"]

    first_author = entry.get("author", "Unknown authors")
    first_author = first_author.split(",")[0]

    label = "<<B>%s" % html.escape(first_author)
    if "year" in entry:
        label += " (%s)" % entry["year"]

    label += "</B><BR/>" + html.escape("\n".join(textwrap.wrap(title, width=20))).replace("\n", "<BR/>") + ">"

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
