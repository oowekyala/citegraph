import html
import textwrap

import graphviz as g

from citegraph.model import Biblio, Paper, Person, SEMAPI_ID_FIELD

UNKNOWN_PERSON = Person(string="Unknown von Nowhere")
READ_BIB_KEY = "_read"


DOT_FORMAT = "dot"

class GraphBuilder(object):

    def __init__(self, bibdata: Biblio, title="Citation graph"):
        self.dot = g.Digraph(title)
        self.bibdata = bibdata


    def get_node_attributes(self, paper_entry: Paper):
        attrs = {}

        if paper_entry in self.bibdata:
            attrs["style"] = "filled"

            if paper_entry.fields.get(READ_BIB_KEY, "") == "true":
                attrs["fillcolor"] = "lightblue"
            else:
                attrs["fillcolor"] = "lightyellow"
        else:
            attrs["style"] = "dashed"

        attrs["URL"] = f"https://www.semanticscholar.org/paper/{paper_entry.fields[SEMAPI_ID_FIELD]}"

        return attrs


    def make_label(self, entry: Paper):
        fields = entry.fields
        title = fields["title"]
        title = "\n".join(textwrap.wrap(title, width=20))

        first_author: Person = next(iter(entry.persons["author"] or []), None) or UNKNOWN_PERSON

        label = "<<B>%s" % html.escape(first_author.last_names[0])
        if "year" in fields:
            label += " (%s)" % fields["year"]

        label += "</B><BR/>" + html.escape(title).replace("\n", "<BR/>") + ">"

        return label


    def add_paper(self, paper_entry: Paper):

        self.dot.node(name=paper_entry.key,
                      label=self.make_label(paper_entry),
                      **self.get_node_attributes(paper_entry))


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


    def cite(self, src_entry: Paper, dst_entry: Paper):
        self.bibdata.norm_key(src_entry)
        self.bibdata.norm_key(dst_entry)
        self.dot.edge(src_entry.key, dst_entry.key, **self.get_edge_attributes(src_entry, dst_entry))


    def make_entry(self, paper_dict) -> Paper:
        return self.bibdata.make_entry(paper_dict)


    def render(self, filename, render_format):
        if render_format == "dot":
            self.dot.save(filename=filename)
            print("DOT saved in " + filename)
        else:
            print("Rendering...")
            self.dot.render(filename=filename, format=render_format)
            print("Rendered to " + filename + "." + render_format)
