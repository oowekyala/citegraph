import graphviz as g
import bibtexparser as btex
from bibtexparser.bibdatabase import BibDatabase
from typing import NamedTuple
import sys, os, textwrap, getopt, html

DEFAULT_FORMAT = "pdf"



class Args(NamedTuple):
    dotfile: str
    renderfile: str
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



def parse_args(argv) -> Args:
    (opt_dotfile, opt_dotfile_short) = ("dotfile", "d")
    (opt_bibfile, opt_bibfile_short) = ("bibfile", "i")
    (opt_format_short) = "f"
    (opt_render_out_short) = "o"


    def usage():
        print("Usage:")
        print("  citegraph.py -%s <file>.bib -%s <graph>.dot" % (opt_bibfile_short, opt_dotfile_short))
        print("  citegraph.py --%s <file>.bib --%s <graph>.dot" % (opt_bibfile, opt_dotfile))
        print("Available formats: %s" % g.FORMATS)


    bibfile = None
    dotfile = None
    render_out = None
    format = DEFAULT_FORMAT
    try:
        opts, args = getopt.getopt(argv,
                                   "h%s:%s:%s:%s:" % (
                                       opt_bibfile_short, opt_dotfile_short, opt_format_short, opt_render_out_short),
                                   ["%s=" % opt_bibfile, "%s=" % opt_dotfile])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            usage()
            sys.exit()
        elif opt in ("-" + opt_bibfile_short, "--" + opt_bibfile):
            if not render_out:
                render_out = os.path.splitext(arg)[0]
            bibfile = arg
        elif opt in ("-" + opt_dotfile_short, "--" + opt_dotfile):
            dotfile = arg
        elif opt == opt_format_short:
            format = arg
        elif opt == opt_render_out_short:
            render_out = opt

    if not bibfile:
        print("Missing .bib file as input")
        usage()
        sys.exit(2)

    return Args(bibfile=bibfile,
                dotfile=dotfile,
                renderformat=format,
                renderfile=render_out
                )



if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    graph = to_dot(args.bibfile)
    if args.dotfile:
        graph.save(filename=args.dotfile)

    graph.render(filename=args.renderfile, format=args.renderformat)
