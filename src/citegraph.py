import graphviz as g
from typing import NamedTuple
import os

import semscholar as semapi
import pybtex.database as bibtex
from pybtex.database.input.bibtex import Parser as BibParser

# Generate a citation graph from a bibtex bibliography

# Citations need to be filled in manually inside a `_cites` key of each bibtex entry
# If you mention _read={true}, the node changes color

# TODO
#  * custom DOT attributes for eg books
#  * extensible metadata in bibtex -> format options at call time
#      eg '--tag=old->[style=dotted]', then all entries that have a key "old" are dotted
#  * semanticscholar API may be used to fetch references, but you need a paper ID

DEFAULT_FORMAT = "pdf"

class Args(NamedTuple):
    dotfile: str
    output_file: str
    renderformat: str
    bibfile: str
    rootid: str

def parse_args() -> Args:
    from optparse import OptionParser
    parser = OptionParser(usage="usage: %prog [options] file.bib root_paper_id")
    parser.add_option("-f", "--format", help="Render format, one of %s" % g.FORMATS, metavar="FORMAT", default=DEFAULT_FORMAT)
    parser.add_option("-d", "--dotfile", help="Dump for generated DOT (default none)", metavar="FILE")
    parser.add_option("-o", "--outfile", help="Path to the rendered file (default next to bib file)", metavar="FILE")

    (options, args) = parser.parse_args()

    if len(args) == 0:
        parser.error("Missing bibtex file")
    elif len(args) > 2:
        parser.error("Expecting two positional argument")

    (bibfile, rootid) = args
    render_file = options.outfile or os.path.splitext(bibfile)[0]

    return Args(
        renderformat=options.format,
        bibfile=bibfile,
        dotfile=options.dotfile,
        output_file=render_file,
        rootid=rootid
    )


if __name__ == "__main__":
    args = parse_args()
    bibdata: bibtex.BibliographyData = BibParser().parse_file(args.bibfile)
    dot_builder = semapi.DotBuilder()
    semapi.build_graph([args.rootid], depth=4, bibdata=bibdata, dot_builder=dot_builder)
    graph: g.Digraph = dot_builder.dot
    if args.dotfile:
        graph.save(filename=args.dotfile)

    graph.render(filename=args.output_file, format=args.renderformat)
