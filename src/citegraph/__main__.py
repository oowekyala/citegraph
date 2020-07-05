import argparse
from pathlib import Path

import os

from citegraph.draw import DotGraphRenderer, GephiGraphRenderer, StylingInfo, SUPPORTED_FORMATS
from citegraph.explore import Params
from citegraph.explore import smart_fetch as create_graph
from citegraph.model import Biblio
from citegraph.semapi import PaperDb

DEFAULT_FORMAT = "pdf"
DB_LOC_VAR = "CITEGRAPH_DB"


def parse_args():
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

    parser.add_argument("-f", "--format", nargs="+", metavar="FORMAT", default=[DEFAULT_FORMAT],
                        help=f"Render format(s), default is '{DEFAULT_FORMAT}'. "
                             f"Must be one of {SUPPORTED_FORMATS}.")
    parser.add_argument("-o", "--outfile", metavar="FILE", default="graph",
                        help="Path to the rendered file, without extension."
                             " The extension is determined based on the render format.")
    parser.add_argument("--size", type=int, help="Size of the graph to generate", metavar="INT", default=80)
    parser.add_argument("--tags", metavar="FILE",
                        help="Path to a yaml file containing styling info. "
                             "See the README for a description of the expected format")
    parser.add_argument("-b", "--bib", dest="bibfile", metavar="FILE.bib",
                        help="Bibtex file, whose contents help guide the graph exploration. "
                             "Entries may contain paper IDs, which are automatically added "
                             "to the roots of the exploration. "
                             "The exploration tries to cover as much of those papers as possible, "
                             "but they much be reachable from the provided roots.")
    parser.add_argument("--db-location", metavar="FILE",
                        help=f"Location of the database file (defaults to environment variable {DB_LOC_VAR})")
    parser.add_argument("graph_roots", metavar="ID", nargs="*",
                        help="Paper IDs for the starting points of the graph exploration")

    parsed = parser.parse_args()

    unknown_formats = set(parsed.format) - set(SUPPORTED_FORMATS)
    if len(unknown_formats) != 0:
        parser.error(f"Unrecognized format(s) {unknown_formats}")

    if len(parsed.format) == 0:
        parsed.format = [DEFAULT_FORMAT]

    if len(parsed.graph_roots) == 0 and not parsed.bibfile:
        parser.error("You must specify the ID of a paper, or a bibtex file that contains such IDs")

    if parsed.bibfile and not Path(parsed.bibfile).is_file():
        parser.error(f"Bibtex file does not exist: {parsed.bibfile}")

    return parsed, parser



def seeds_in_bib(biblio: Biblio):
    seeds = []
    for paper in biblio:
        if paper.paperId:
            seeds.append(paper.paperId)
        elif paper.journal and paper.journal.lower() == "arxiv":
            volume: str = getattr(paper, "volume", "")
            if volume.startswith("abs/"):
                seeds.append("arXiv:" + volume[len("abs/"):])

    return seeds



def main(args, do_error):
    bibdata = Biblio.from_file(args.bibfile) if args.bibfile else Biblio.empty()

    # Complete the given seeds with seeds from the bibtex file
    seeds = {*args.graph_roots, *seeds_in_bib(bibdata)}

    if len(seeds) == 0:
        do_error("No graph roots could be found, mention some on the command-line")

    db_loc = args.db_location or os.getenv(DB_LOC_VAR) or ".citegraph.sqlite"

    with PaperDb(bibdata=bibdata, dbfile=db_loc) as db:
        params = Params(max_graph_size=args.size)
        graph = create_graph(seeds=seeds, biblio=bibdata, params=params, db=db)

    renderer = None
    for f in args.format:
        if f in DotGraphRenderer.supported_formats():
            if not isinstance(renderer, DotGraphRenderer):
                renderer = DotGraphRenderer(bibdata=bibdata, styling=StylingInfo(args.tags))
        elif f in GephiGraphRenderer.supported_formats():
            if not isinstance(renderer, GephiGraphRenderer):
                renderer = GephiGraphRenderer()
        else:
            raise AssertionError(f"Wrong format {args.format}")

        graph.draw(renderer)
        print("Rendering...")
        renderer.render(filename=args.outfile, render_format=f)
        print("Rendered to " + args.outfile + "." + f)



if __name__ == "__main__":
    args, parser = parse_args()
    main(args, parser.error)
