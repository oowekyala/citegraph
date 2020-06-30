import html
import yaml
import textwrap

import graphviz as g

from citegraph.model import *

from abc import ABCMeta, abstractmethod

UNKNOWN_PERSON = Person(string="Unknown von Nowhere")
READ_BIB_KEY = "_read"

DOT_FORMAT = "dot"



class GraphRenderer(object):

    @abstractmethod
    def add_node(self, paper: Paper):
        pass


    @abstractmethod
    def add_edge(self, src: Paper, dst: Paper):
        pass



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



class DotGraphRenderer(GraphRenderer):

    def __init__(self,
                 bibdata: Biblio,
                 styling: StylingInfo,
                 title="Citation graph"):
        self.dot = g.Digraph(title)
        self.bibdata = bibdata
        self.styling = styling


    def get_node_attributes(self, paper: Paper):
        return {
            "URL": f"https://www.semanticscholar.org/paper/{paper.id}",
            **self.styling.get_attributes(paper, self.bibdata)
        }


    def make_label(self, entry: Paper):
        fields = entry.fields
        title = fields["title"]
        title = "\n".join(textwrap.wrap(title, width=20))

        first_author: Person = next(iter(entry.authors), None) or UNKNOWN_PERSON

        label = "<<B>%s" % html.escape(first_author.last_names[0])
        if "year" in fields:
            label += " (%s)" % fields["year"]

        label += "</B><BR/>" + html.escape(title).replace("\n", "<BR/>") + ">"

        return label


    def add_node(self, paper: Paper):

        self.dot.node(name=paper.id,
                      label=self.make_label(paper),
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
            self.dot.save(filename=filename)
            print("DOT saved in " + filename)
        else:
            print("Rendering...")
            self.dot.render(filename=filename, format=render_format)
            print("Rendered to " + filename + "." + render_format)
