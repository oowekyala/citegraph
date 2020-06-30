import os, sys
from typing import NamedTuple

import citegraph.explore as explore
from citegraph.graph import *
from citegraph.semapi import *

# Generate a citation graph from a bibtex bibliography

# Citations need to be filled in manually inside a `_cites` key of each bibtex entry
# If you mention _read={true}, the node changes color

# TODO
#  * custom DOT attributes for eg books
#  * extensible metadata in bibtex -> format options at call time
#      eg '--tag=old->[style=dotted]', then all entries that have a key "old" are dotted

DEFAULT_FORMAT = "pdf"



class Args(NamedTuple):
    dotfile: str
    output_file: str
    renderformat: str
    bibfile: str
    roots: List[PaperId]
    depth: int



def parse_args() -> Args:
    from optparse import OptionParser
    parser = OptionParser(usage="usage: %prog (option)* file.bib (paper_id)+")
    parser.add_option("-f", "--format", help="Render format, one of %s" % g.FORMATS, metavar="FORMAT",
                      default=DEFAULT_FORMAT)
    parser.add_option("-d", "--dotfile", help="Dump for generated DOT (default none)", metavar="FILE")
    parser.add_option("-o", "--outfile", help="Path to the rendered file (default next to bib file)", metavar="FILE")
    parser.add_option("--depth", type="int", help="Depth of the exploration", metavar="INT", default=2)

    (options, args) = parser.parse_args()

    if len(args) == 0:
        parser.error("Missing bibtex file")

    bibfile = args[0]
    render_file = options.outfile or os.path.splitext(bibfile)[0]

    return Args(
        renderformat=options.format,
        bibfile=bibfile,
        dotfile=options.dotfile,
        output_file=render_file,
        roots=args[1:],
        depth=options.depth
    )



if __name__ == "__main__":
    args = parse_args()
    bibdata = Biblio.from_file(args.bibfile)
    dot_builder = GraphBuilder(bibdata=bibdata)
    db = PaperDb(bibdata=bibdata)
    explore.astar(seeds=args.roots,
                  max_size=args.depth * 40,
                  builder=dot_builder,
                  db=db)

    if args.dotfile:
        dot_builder.render(filename=args.dotfile, render_format=DOT_FORMAT)

    dot_builder.render(filename=args.output_file, render_format=args.renderformat)
