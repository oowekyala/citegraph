import html
import textwrap

import graphviz as g
import yaml

from citegraph.model import *
from abc import abstractmethod


UNKNOWN_PERSON = Person(string="Unknown von Nowhere")


class GraphRenderer(object):
    """Renders a graph somewhere."""


    @abstractmethod
    def add_node(self, paper: Paper):
        pass


    @abstractmethod
    def add_edge(self, src: Paper, dst: Paper):
        pass


    @abstractmethod
    def render(self, filename, render_format):
        pass



class Graph(object):

    def __init__(self, nodes: Dict[PaperId, PaperAndRefs]):
        self.nodes = nodes

        # successors[p1.id][p2.id] means there is a directed edge p1 -> p2
        self.successors = {}

        for paper in self.nodes.values():
            succs = {}
            self.successors[paper.id] = succs

            for ref in paper.references:
                if ref.id in self.nodes:
                    succs[ref.id] = True

    # todo transitive reduction

    def draw(self, builder: GraphRenderer):
        for paper in sorted(self.nodes.values(), key=lambda p: p.id):
            builder.add_node(paper)
            for ref in paper.references:
                if ref.id in self.nodes:
                    builder.add_edge(paper, ref)


class StylingInfo(object):

    def __init__(self, filename):
        self._by_id = {}
        self._tags = {}
        self.selectors_by_tag = {}

        if filename:
            with open(filename) as file:
                doc = yaml.load(file)
                self.categorize(doc)

    def add_tag(self, name, attrs, selector_fun):
        self._tags[name] = attrs
        self.selectors_by_tag[name] = selector_fun


    def categorize(self, yaml_doc):
        self.add_tag("default_outside_bib",
                     attrs={"style": "dashed"},
                     selector_fun=lambda p, biblio: p not in biblio
                     )

        for tag, body in yaml_doc.get("tags", {}).items():
            print(f"processing {tag}")
            attrs = body.get("attrs", {})

            for id in body.get("members", []):
                prev_attrs = self._by_id.get(id, {})
                self._by_id[id] = {**prev_attrs, **attrs}


            def selects(members, selector):
                return lambda p, biblio: p.bibtex_id in members\
                       or eval(selector, {"paper": p})


            self.add_tag(tag, attrs, selector_fun=selects(body.get("members", []), body.get("selector", "False")))


    def get_attributes(self, paper: Paper, biblio: Biblio):
        attrs = {}

        for tag, selector in self.selectors_by_tag.items():
            if selector(paper, biblio):
                attrs.update(self._tags[tag])

        attrs.update(self._by_id.get(paper.bibtex_id, {}))

        return attrs



def make_label(entry: Paper):
    fields = entry.fields
    title = fields["title"]
    title = "\n".join(textwrap.wrap(title, width=20))

    first_author: Person = next(iter(entry.authors), None) or UNKNOWN_PERSON

    label = "<<B>%s" % html.escape(first_author.last_names[0])
    if "year" in fields:
        label += " (%s)" % fields["year"]

    label += "</B><BR/>" + html.escape(title).replace("\n", "<BR/>") + ">"

    return label



class DotGraphRenderer(GraphRenderer):

    def __init__(self,
                 bibdata: Biblio,
                 styling: StylingInfo,
                 title="Citation graph"):
        self.dot = g.Digraph(title)
        self.bibdata = bibdata
        self.styling = styling

    @classmethod
    def supported_formats(cls):
        return [*g.FORMATS, "dot"]


    def get_node_attributes(self, paper: Paper):
        return {
            "URL": f"https://www.semanticscholar.org/paper/{paper.id}",
            **self.styling.get_attributes(paper, self.bibdata)
        }


    def add_node(self, paper: Paper):

        self.dot.node(name=paper.id,
                      label=make_label(paper),
                      **self.get_node_attributes(paper))


    def get_edge_attributes(self, src: Paper, dst: Paper):
        attrs = {}

        src_in_bib = src in self.bibdata
        dst_in_bib = dst in self.bibdata
        # if src_in_bib ^ dst_in_bib:
        #     attrs["color"] = "black;0.25:gray" if src_in_bib else "gray;0.75:black"
        # elif
        if not src_in_bib or not dst_in_bib:
            attrs["color"] = "gray"
        else:
            attrs["weight"] = "2"

        return attrs


    def add_edge(self, src: Paper, dst: Paper):
        self.dot.edge(src.id, dst.id, **self.get_edge_attributes(src, dst))


    def render(self, filename, render_format):
        if render_format == "dot":
            self.dot.save(filename=filename + ".dot")
            print("DOT saved in " + filename)
        else:
            print("Rendering...")
            self.dot.render(filename=filename, format=render_format)
            print("Rendered to " + filename + "." + render_format)



class GephiGraphRenderer(GraphRenderer):

    def __init__(self):
        self.nodes = []
        self.edges = []

    @classmethod
    def supported_formats(cls):
        return ["gexf"]


    def add_node(self, paper: Paper):
        self.nodes.append(
            f"<node id='{paper.id}' label='{make_label(paper)}' />"
        )


    def add_edge(self, src: Paper, dst: Paper):
        self.edges.append(
            f"<edge id='{len(self.edges)}' source='{src.id}' target='{dst.id}' />"
        )


    def render(self, filename, render_format):
        assert render_format in ["gexf", "gephi"], f"Unsupported format {render_format}"

        with open('w', filename + ".gexf") as f:
            f.write("""

<?xml version="1.0" encoding="UTF-8"?>
<gexf xmlns="http://www.gexf.net/1.2draft" version="1.2">
    <graph mode="static" defaultedgetype="directed">
        <nodes>
            {nodes}
        </nodes>
        <edges>
            {edges}
        </edges>
    </graph>
</gexf>
""".format_map({
                "nodes": ("\n" + ' ' * 4 * 3).join(self.nodes),
                "edges": ("\n" + ' ' * 4 * 3).join(self.edges)
            }))


SUPPORTED_FORMATS = [*DotGraphRenderer.supported_formats(),
                     *GephiGraphRenderer.supported_formats()]
