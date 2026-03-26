"""
Healthcare Credentialing Demo — Healthcare Provider Credentialing Knowledge Graph
=================================================================
Demonstrates:
  1. Data cleansing   — normalise names, NPIs, dates, states; remove duplicates
  2. OWL ontology     — build an rdflib graph with classes and object properties
  3. Knowledge graph  — project to NetworkX and visualise as PNG + interactive HTML

Usage:
    cd certify_demo
    python main.py
"""

import sys
from pathlib import Path

# Make certify_demo/ importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from data.dirty_providers     import load_dirty_records
from cleanse.cleaner          import clean_providers, cleansing_report
from cleanse.report_html      import save_cleansing_report
from ontology.builder         import build_ontology
from graph.visualizer         import build_networkx_graph, draw_static, draw_interactive

OUTPUT_DIR = Path(__file__).parent / "output"

# ── Formatting helpers ────────────────────────────────────────────────────────

def _banner(title: str) -> None:
    width = 65
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def _print_stats(stats: dict) -> None:
    print(f"\n  {'Raw records loaded':<28} {stats['total_raw']:>4}")
    print(f"  {'Clean records kept':<28} {stats['total_clean']:>4}")
    print(f"  {'Duplicates removed':<28} {stats['duplicates_removed']:>4}")
    print(f"  {'Invalid NPIs found':<28} {stats['invalid_npis_fixed']:>4}")

    print("\n  Null counts  before -> after  (per field):")
    before = stats["null_counts_before"]
    after  = stats["null_counts_after"]
    for field in sorted(set(before) | set(after)):
        b = before.get(field, 0)
        a = after.get(field, 0)
        flag = " *" if b > 0 and a < b else ("  " if b == a else " !")
        print(f"    {flag} {field:<22} {b:>3}  ->  {a:>3}")


# ── Cleansing demo ────────────────────────────────────────────────────────────

def _print_cleansing_demo(raw_records: list) -> None:
    """Print a field-by-field before/after diff for every record."""
    reports = cleansing_report(raw_records)

    status_counts = {"cleaned": 0, "duplicate": 0, "unchanged": 0}
    for rep in reports:
        status_counts[rep["status"]] += 1

    print(f"\n  {len(reports)} records processed:")
    print(f"    {status_counts['cleaned']:>2} changed    "
          f"{status_counts['duplicate']:>2} duplicates removed    "
          f"{status_counts['unchanged']:>2} already clean")

    W = 72
    for rep in reports:
        idx    = rep["index"]
        name   = str(rep["name"]) if rep["name"] else "(no name)"
        status = rep["status"]

        print("\n  " + "-" * W)

        if status == "duplicate":
            dup_of = rep.get("duplicate_of", "?")
            print(f"  Record #{idx:>2}  [{name}]")
            print(f"  [REMOVED] Duplicate of record #{dup_of} (same NPI after normalisation)")
            # Still show what would have been cleaned
            if rep["changes"]:
                for ch in rep["changes"]:
                    print(f"            {ch['field']:<18}  \"{ch['before']}\"  ->  \"{ch['after']}\"")
            continue

        if status == "unchanged":
            print(f"  Record #{idx:>2}  [{name}]  -- no changes needed --")
            continue

        print(f"  Record #{idx:>2}  [{name}]  [{len(rep['changes'])} field(s) changed]")
        for ch in rep["changes"]:
            before = ch["before"]
            after  = ch["after"]
            rule   = ch["rule"]
            print(f"    {ch['field']:<18}  \"{before}\"")
            print(f"    {'':18}  ->  \"{after}\"")
            print(f"    {'':18}      ({rule})")

    print("\n  " + "-" * W)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def main(data_path: str = None) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    _banner("Healthcare Credentialing Demo - Healthcare Provider Knowledge Graph")

    # ── Stage 1: Cleanse ──────────────────────────────────────────────────────
    print("\n[1/4]  Loading and cleansing dirty provider data...")
    raw_records = load_dirty_records(data_path)
    print(f"  Source: {data_path or 'data/dirty_providers.json'}")
    df, stats = clean_providers(raw_records)
    _print_stats(stats)

    print("\n  --- CLEANSING WALKTHROUGH (record by record) ---")
    _print_cleansing_demo(raw_records)

    print("\n  Generating cleansing HTML report...")
    reports = cleansing_report(raw_records)
    save_cleansing_report(
        raw_records, reports, df,
        str(OUTPUT_DIR / "cleansing_report.html"),
    )

    print("\n  Final cleaned records:")
    display_cols = ["name", "npi", "credential_type", "state", "specialty", "organization"]
    print(df[display_cols].fillna("-").to_string(index=False))

    # ── Stage 2: Build ontology ───────────────────────────────────────────────
    print("\n[2/4]  Building OWL ontology (rdflib)...")
    rdf_g = build_ontology(df)
    print(f"  Total triples in graph : {len(rdf_g)}")

    # ── Stage 3: Project to NetworkX ──────────────────────────────────────────
    print("\n[3/4]  Projecting ontology -> NetworkX DiGraph...")
    nx_g = build_networkx_graph(rdf_g)
    print(f"  Nodes  : {nx_g.number_of_nodes()}")
    print(f"  Edges  : {nx_g.number_of_edges()}")

    node_types = {}
    for _, data in nx_g.nodes(data=True):
        t = data.get("node_type", "Unknown")
        node_types[t] = node_types.get(t, 0) + 1
    print("\n  Node breakdown:")
    for t, count in sorted(node_types.items()):
        print(f"    {t:<24} {count:>3}")

    # ── Stage 4: Visualise ────────────────────────────────────────────────────
    print("\n[4/4]  Generating visualizations...")
    draw_static(      nx_g, str(OUTPUT_DIR / "knowledge_graph.png"))
    draw_interactive( nx_g, str(OUTPUT_DIR / "knowledge_graph.html"))

    print(f"\n  Output directory : {OUTPUT_DIR.resolve()}")
    print("\nDone.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Healthcare Credentialing Demo")
    parser.add_argument(
        "--data", metavar="FILE",
        help="Path to a JSON file of provider records (default: data/dirty_providers.json)"
    )
    args = parser.parse_args()
    main(data_path=args.data)
