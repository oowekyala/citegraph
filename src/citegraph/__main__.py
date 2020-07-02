from pathlib import Path

import citegraph.explore as explore
from citegraph.draw import *
from citegraph.semapi import *

DEFAULT_FORMAT = "pdf"



def parse_args():
    import argparse
    parser = argparse.ArgumentParser(
        prog="citegraph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=f"""
    Builds a citation graph from a set of initial papers. Those
    can be specified in one of two ways:
    - By mentioning paper IDs as positional arguments
    - By using the --bibfile option, where at least one entry in the
     BibTeX file has a 'paperId' field, or an arXiv ID.

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

    $ citegraph --bibfile biblio.bib CorpusID:37220927
    $ citegraph CorpusID:37220927
    $ citegraph CorpusID:37220927 arXiv:1705.10311

                          """.rstrip(),
        epilog="""

    Report issues at https://github.com/oowekyala/citegraph                                     

    """.rstrip())

    parser.add_argument("-f", "--format", help="Render format, one of %s" % SUPPORTED_FORMATS, metavar="FORMAT",
                        default=DEFAULT_FORMAT)
    parser.add_argument("-o", "--outfile", help="Path to the rendered file, without extension (default 'graph')",
                        metavar="FILE")
    parser.add_argument("--size", type=int, help="Size of the graph to generate", metavar="INT", default=80)
    parser.add_argument("--tags", help="Path to a yaml file containing styling info", metavar="FILE")
    parser.add_argument("--old", help="Use old generation scheme", action="store_true")
    parser.add_argument("-b", "--bib", dest="bibfile", metavar="file.bib",
                        help="Bibtex file, whose contents help guide the graph exploration")
    parser.add_argument("graph_roots", metavar="ID", nargs="*",
                        help="Paper IDs for the starting points of the graph exploration")

    parsed = parser.parse_args()

    parsed.outfile = parsed.outfile or "graph"

    if parsed.format not in SUPPORTED_FORMATS:
        parser.error(f"Unrecognized format {parsed.format}")

    if len(parsed.graph_roots) == 0 and not parsed.bibfile:
        parser.error("You must specify the ID of a paper, or a bibtex file that contains such ids")

    if parsed.bibfile and not Path(parsed.bibfile).is_file():
        parser.error(f"Bibtex file does not exist: {parsed.bibfile}")

    return parsed



if __name__ == "__main__":
    args = parse_args()

    bibdata = Biblio.from_file(args.bibfile) if args.bibfile else Biblio.empty()
    db = PaperDb(bibdata=bibdata)
    fun = explore.initialize_graph if args.old else explore.smart_fetch
    graph = fun(seeds=args.graph_roots,
                biblio=bibdata,
                max_size=args.size,
                db=db)

    if graph:
        if args.format in DotGraphRenderer.supported_formats():
            dot_builder = DotGraphRenderer(bibdata=bibdata, styling=StylingInfo(args.tags))
        elif args.format in GephiGraphRenderer.supported_formats():
            dot_builder = GephiGraphRenderer()
        else:
            raise AssertionError(f"Wrong format {args.format}")

        graph.draw(dot_builder)
        dot_builder.render(filename=args.outfile, render_format=args.format)
