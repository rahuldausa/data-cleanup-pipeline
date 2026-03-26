"""
Knowledge graph visualization using NetworkX, Matplotlib, and PyVis.

draw_static()       -> saves a PNG (reproducible layout, seed=42)
draw_interactive()  -> saves an HTML file with drag/zoom/hover via PyVis
"""

import networkx as nx
import matplotlib
matplotlib.use("Agg")           # Non-interactive backend (headless-friendly)
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from rdflib import Graph, Namespace, RDFS, RDF

CERT = Namespace("http://healthcare-demo.example.org/ontology#")

OBJECT_PROPS = [
    CERT.hasCredential,
    CERT.hasSpecialty,
    CERT.worksAt,
    CERT.licensedIn,
]

NODE_COLORS = {
    "Physician":            "#4A90D9",
    "NursePractitioner":    "#7B68EE",
    "MedicalLicense":       "#F5A623",
    "BoardCertification":   "#F8E71C",
    "DEARegistration":      "#D0021B",
    "Specialty":            "#7ED321",
    "State":                "#9B9B9B",
    "Organization":         "#BD10E0",
    "Unknown":              "#CCCCCC",
}

NODE_SIZES = {
    "Physician":            900,
    "NursePractitioner":    900,
    "MedicalLicense":       550,
    "BoardCertification":   550,
    "DEARegistration":      550,
    "Specialty":            650,
    "State":                650,
    "Organization":         650,
    "Unknown":              400,
}

# ── RDF helpers ────────────────────────────────────────────────────────────────

def _get_label(g: Graph, uri) -> str:
    label = g.value(uri, RDFS.label)
    if label:
        return str(label)
    s = str(uri)
    return s.split("#")[-1] if "#" in s else s.rstrip("/").split("/")[-1]


def _get_type_name(g: Graph, uri) -> str:
    type_uri = g.value(uri, RDF.type)
    if type_uri:
        s = str(type_uri)
        return s.split("#")[-1] if "#" in s else s.rstrip("/").split("/")[-1]
    return "Unknown"


# ── Graph construction ────────────────────────────────────────────────────────

def build_networkx_graph(rdf_graph: Graph) -> nx.DiGraph:
    """
    Project object-property triples from an rdflib Graph into a NetworkX DiGraph.
    Only object properties are included (literal/datatype nodes are skipped)
    so the visualization stays meaningful.
    """
    G = nx.DiGraph()
    for prop in OBJECT_PROPS:
        prop_label = str(prop).split("#")[-1]
        for s, o in rdf_graph.subject_objects(prop):
            s_key   = str(s)
            o_key   = str(o)
            s_label = _get_label(rdf_graph, s)
            o_label = _get_label(rdf_graph, o)
            s_type  = _get_type_name(rdf_graph, s)
            o_type  = _get_type_name(rdf_graph, o)

            G.add_node(s_key, label=s_label, node_type=s_type)
            G.add_node(o_key, label=o_label, node_type=o_type)
            G.add_edge(s_key, o_key, label=prop_label)
    return G


# ── Static PNG ────────────────────────────────────────────────────────────────

def draw_static(G: nx.DiGraph, output_path: str) -> None:
    """Render the graph as a static matplotlib PNG."""
    pos         = nx.spring_layout(G, seed=42, k=2.8)
    node_colors = [NODE_COLORS.get(G.nodes[n].get("node_type", "Unknown"), "#CCCCCC") for n in G.nodes]
    node_sizes  = [NODE_SIZES.get(G.nodes[n].get("node_type", "Unknown"), 400) for n in G.nodes]
    labels      = {n: G.nodes[n].get("label", n.split("/")[-1]) for n in G.nodes}
    edge_labels = {(u, v): d["label"] for u, v, d in G.edges(data=True)}

    fig, ax = plt.subplots(figsize=(20, 13))
    fig.patch.set_facecolor("#f8f9fa")
    ax.set_facecolor("#f8f9fa")

    nx.draw_networkx_nodes(
        G, pos,
        node_color=node_colors,
        node_size=node_sizes,
        ax=ax,
        alpha=0.92,
        linewidths=1.5,
        edgecolors="#333333",
    )
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=7, ax=ax, font_weight="bold")
    nx.draw_networkx_edges(
        G, pos, ax=ax,
        arrows=True, arrowsize=16,
        edge_color="#666666", alpha=0.55,
        connectionstyle="arc3,rad=0.12",
        width=1.2,
    )
    nx.draw_networkx_edge_labels(
        G, pos, edge_labels=edge_labels,
        font_size=6, ax=ax, label_pos=0.38,
        font_color="#333333",
        bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.6, ec="none"),
    )

    legend_patches = [
        mpatches.Patch(color=color, label=ntype, linewidth=0.5, edgecolor="#333")
        for ntype, color in NODE_COLORS.items()
        if ntype != "Unknown"
    ]
    ax.legend(handles=legend_patches, loc="upper left", fontsize=9,
              framealpha=0.9, title="Node Type", title_fontsize=9)

    ax.set_title(
        "Healthcare Provider Credentialing Knowledge Graph",
        fontsize=14, fontweight="bold", pad=16,
    )
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved static PNG     -> {output_path}")


# ── Interactive HTML ──────────────────────────────────────────────────────────

def draw_interactive(G: nx.DiGraph, output_path: str) -> None:
    """Render an interactive PyVis HTML with drag, zoom, and hover tooltips."""
    try:
        from pyvis.network import Network
    except ImportError:
        print("  pyvis not installed — skipping interactive HTML.")
        return

    net = Network(
        height="800px", width="100%",
        directed=True,
        bgcolor="#1a1a2e",
        font_color="white",
    )

    for node_id in G.nodes:
        node  = G.nodes[node_id]
        ntype = node.get("node_type", "Unknown")
        label = node.get("label", node_id.split("/")[-1])
        color = NODE_COLORS.get(ntype, "#CCCCCC")
        size  = NODE_SIZES.get(ntype, 400) // 30
        title = f"<b>{label}</b><br><span style='color:#aaa'>Type: {ntype}</span>"
        net.add_node(node_id, label=label, color=color, size=size, title=title)

    for src, dst, data in G.edges(data=True):
        net.add_edge(
            src, dst,
            label=data.get("label", ""),
            arrows="to",
            font={"size": 9, "color": "#cccccc"},
            color={"color": "#555555", "highlight": "#aaaaaa"},
        )

    net.set_options("""
    {
      "physics": {
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -80,
          "centralGravity": 0.01,
          "springLength": 130,
          "springConstant": 0.08,
          "damping": 0.4
        },
        "minVelocity": 0.75
      },
      "edges": {
        "smooth": { "type": "curvedCW", "roundness": 0.2 }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 100
      }
    }
    """)

    net.write_html(output_path)
    print(f"  Saved interactive HTML -> {output_path}")
