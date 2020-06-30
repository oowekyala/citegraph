import os

import citegraph.explore as explore
from citegraph.draw import *
from citegraph.semapi import *

from pathlib import Path

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
    initial_size: int



def parse_args() -> Args:
    import argparse
    parser = argparse.ArgumentParser(prog="citegraph",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=f"""
    The mentioned paper IDs are the roots for the graph exploration.
    Exploration will start from those and try to cover as much of the
    contents of the bibliography file as possible.

    You can obtain a paper ID from semanticscholar.org. 
    Examples of valid ID formats:

    S2 Paper ID : 0796f6cd7f0403a854d67d525e9b32af3b277331
    DOI         : 10.1038/nrn3241
    ArXiv ID    : arXiv:1705.10311
    MAG ID      : MAG:112218234
    ACL ID      : ACL:W12-3903
    PubMed ID   : PMID:19872477
    Corpus ID   : CorpusID:37220927

    Examples:

    $ citegraph biblio.bib CorpusID:37220927

                          """.rstrip(),
                                     epilog="""

    Report issues at https://github.com/oowekyala/citegraph                                     

    """.rstrip())
    parser.add_argument("-f", "--format", help="Render format, one of %s" % g.FORMATS, metavar="FORMAT",
                        default=DEFAULT_FORMAT)
    parser.add_argument("-d", "--dotfile", help="Dump for generated DOT (default none)", metavar="FILE")
    parser.add_argument("-o", "--outfile", help="Path to the rendered file (default next to bib file)", metavar="FILE")
    parser.add_argument("--initial-size", type=int, help="Size of the graph to generate",
                        metavar="INT", default=80)

    parser.add_argument("bibfile", metavar="file.bib", help="Bibtex file")
    parser.add_argument("graph_roots", metavar="ID", nargs="+", help="Paper IDs")

    parsed = parser.parse_args()

    parsed.outfile = parsed.outfile or os.path.splitext(parsed.bibfile)[0]

    if not Path(parsed.bibfile).is_file():
        parser.error(f"Bibtex file does not exist: {parsed.bibfile}")

    return Args(
        renderformat=parsed.format,
        bibfile=parsed.bibfile,
        dotfile=parsed.dotfile,
        output_file=parsed.outfile,
        roots=parsed.graph_roots,
        initial_size=parsed.initial_size
    )



if __name__ == "__main__":
    args = parse_args()

    bibdata = Biblio.from_file(args.bibfile)
    db = PaperDb(bibdata=bibdata)
    graph = explore.initialize_graph(seeds=args.roots,
                                     biblio=bibdata,
                                     max_size=args.initial_size,
                                     db=db)

    dot_builder = DotGraphRenderer(bibdata=bibdata)
    graph.draw(dot_builder)

    if args.dotfile:
        dot_builder.render(filename=args.dotfile, render_format=DOT_FORMAT)

    dot_builder.render(filename=args.output_file, render_format=args.renderformat)
