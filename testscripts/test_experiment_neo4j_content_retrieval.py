#!/usr/bin/env python3
"""
Diagnostic test script for "experiment retrieve the content from neo4j".

Purpose (per user request):
- Reproduce the exact workflow between the Experiments API and Neo4j.
- Inspect what the list endpoint (`/experiments`) actually returns (metadata only, sourceFile filename, NO full document text).
- Directly query Neo4j for Experiment + linked :Knowledge / :KnowledgeChunk by experiment_id.
- Print whether 'text' (the document content) is present, its length, embedding_method, node labels.
- Compare "what the API shape would give" vs raw neo4j rows.
- Helps identify why the Experiments page still cannot show the document content.

Run (from repo root or backend dir):
    cd backend
    python ../testscripts/test_experiment_neo4j_content_retrieval.py

It uses the same Neo4j connection settings as the app.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Make backend importable
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

# Lazy imports -- only when actually running main() against live DB
def _get_db_imports():
    try:
        from neo4j import GraphDatabase
        from app.core.config import settings
        from app.db.neo4j_client import Neo4jClient
        return GraphDatabase, settings, Neo4jClient
    except Exception as e:
        print("Import error. Make sure you run with the backend python env (or docker) that has neo4j + app packages.")
        print(e)
        raise


def get_driver(GraphDatabase, settings):
    uri = settings.NEO4J_URI or "bolt://localhost:7687"
    user = settings.NEO4J_USER or "neo4j"
    password = settings.NEO4J_PASSWORD or "password"
    return GraphDatabase.driver(uri, auth=(user, password))


def print_experiment_summary(exp: Dict[str, Any]):
    print(f"  ID: {exp.get('id')}")
    print(f"  description: {exp.get('description')}")
    print(f"  source_file: {exp.get('source_file')}")
    print(f"  kind: {exp.get('kind')}")
    print(f"  status: {exp.get('status')}")
    print(f"  embedding_approach: {exp.get('embedding_approach')}")
    print(f"  created_at: {exp.get('created_at')}")


def main():
    print("=" * 70)
    print("EXPERIMENT -> NEO4J CONTENT RETRIEVAL DIAGNOSTIC")
    print("=" * 70)

    GraphDatabase, settings, Neo4jClient = _get_db_imports()
    driver = get_driver(GraphDatabase, settings)
    client = Neo4jClient(
        uri=settings.NEO4J_URI or "bolt://localhost:7687",
        user=settings.NEO4J_USER or "neo4j",
        password=settings.NEO4J_PASSWORD or "password",
    )

    with driver.session() as session:
        # 1. Simulate /api/v1/experiments list (what the page receives first)
        print("\n[1] Simulating GET /api/v1/experiments (list) - direct neo4j equivalent")
        list_cypher = """
        MATCH (e:Experiment)
        WITH e ORDER BY coalesce(e.created_at, datetime('1900-01-01')) DESC
        RETURN collect(e) AS items, count(e) AS total
        LIMIT 1
        """
        list_res = session.run(list_cypher).single()
        items = list_res["items"] if list_res else []
        total = list_res["total"] if list_res else 0
        print(f"Total experiments in DB (approx): {total}")
        print(f"First page items returned by list logic: {len(items)}")

        if not items:
            print("No experiments found. Create some via the Ingest flow first.")
            return

        # Show what the list actually returns (metadata + sourceFile only)
        sample = dict(items[0])
        print("\nSample item structure from list (this is what frontend receives for the list):")
        print({k: str(v)[:80] for k, v in sample.items() if k in ("id", "description", "source_file", "kind", "status", "embedding_approach")})
        print("NOTE: NO 'text' or full document content in the list response. source_file is only the filename.")

        # Pick first experiment for deep dive
        first_exp = dict(items[0])
        eid = first_exp["id"]
        source = first_exp.get("source_file")

        print(f"\n[2] Deep dive on experiment id={eid} (source_file={source})")

        # 2. What the detail "chunks" endpoint does (the real content retrieval)
        print("\n[2a] Simulating GET /experiments/{id}/chunks via list_chunks_for_experiment logic")
        chunks = client.list_chunks_for_experiment(eid)
        print(f"Number of rows returned (parents + children): {len(chunks)}")

        knowledge_rows = [r for r in chunks if r.get("node_type") == "knowledge" or "Knowledge" in str(r.get("labels", ""))]
        chunk_rows = [r for r in chunks if r.get("node_type") == "knowledge_chunk"]

        print(f"  - :Knowledge (parent/window) rows: {len(knowledge_rows)}")
        print(f"  - :KnowledgeChunk rows: {len(chunk_rows)}")

        if knowledge_rows:
            print("\n  First knowledge/parent row (this should contain the full document text):")
            k0 = dict(knowledge_rows[0])
            print(f"    id={k0.get('id')}")
            print(f"    embedding_method={k0.get('embedding_method')}")
            print(f"    experiment_id={k0.get('experiment_id')}")
            txt = k0.get("text") or ""
            print(f"    text length: {len(txt)}")
            print(f"    text[:150]: {txt[:150]!r} ...")

        if chunk_rows:
            print("\n  First child chunk row:")
            c0 = dict(chunk_rows[0])
            print(f"    chunk_index={c0.get('chunk_index')}")
            print(f"    embedding_method={c0.get('embedding_method')}")
            txt = c0.get("text") or ""
            print(f"    text length: {len(txt)}")
            print(f"    text[:80]: {txt[:80]!r} ...")

        # 3. Direct neo4j query for the same (raw)
        print("\n[2b] Direct Neo4j query for Knowledge linked by experiment_id (raw rows)")
        direct_cypher = """
        MATCH (k:Knowledge {experiment_id: $eid})
        OPTIONAL MATCH (k)-[:HAS_CHUNK]->(c:KnowledgeChunk)
        RETURN k AS parent, collect(c) AS children
        """
        direct = session.run(direct_cypher, eid=eid).single()
        if direct:
            parent = dict(direct["parent"]) if direct["parent"] else None
            children = [dict(c) for c in (direct["children"] or []) if c]
            if parent:
                print(f"  Parent Knowledge found via direct query. Has 'text'? {bool(parent.get('text'))} len={len(parent.get('text') or '')}")
            print(f"  Direct children count: {len(children)}")

        # 4. Also check the "original upload" path (what OriginalDocumentSection often relies on)
        print("\n[3] Check upload placeholder (used by getText kind=upload and ingest)")
        if source:
            upload_cypher = """
            MATCH (k:Knowledge {source_file: $sf, embedding_method: 'Upload'})
            RETURN k
            ORDER BY k.created_at DESC LIMIT 1
            """
            up = session.run(upload_cypher, sf=source).single()
            if up and up["k"]:
                up_node = dict(up["k"])
                print(f"  Upload node exists for source. text len = {len(up_node.get('text') or '')}")
            else:
                print("  No Upload (embedding_method='Upload') node found for this source_file.")
                print("  This explains why 'Original Uploaded' section may be empty.")

        # 5. Summary of the list endpoint behavior
        print("\n[4] Conclusion for the list endpoint")
        print("  The /api/v1/experiments list (and its frontend table) ONLY returns Experiment metadata.")
        print("  'sourceFile' is a filename string used as a key to fetch real content later.")
        print("  Full document text lives in :Knowledge.text (experiment_id or source_file).")
        print("  If the detail document sections are blank, the issue is in the chunks or /documents/.../text path for this experiment_id/source.")

    driver.close()
    print("\n" + "=" * 70)
    print("Done. Use this output + browser DevTools (Network tab on the experiments page)")
    print("to compare what the real frontend receives.")
    print("=" * 70)


if __name__ == "__main__":
    main()


def simulate_expected_output():
    """Dry-run simulation of what a successful run would report for a healthy ingest experiment.
    Call this to see the expected shape without a live DB.
    """
    print("\n=== SIMULATED EXPECTED OUTPUT (for healthy ChildChunk/LongText ingest) ===")
    print("EXP <uuid> yourfile.md")
    print("  KNOWLEDGE LongText 12345 labels= ['Knowledge'] text[:100]= 'Full document content here... '")
    print("  KNOWLEDGE ChildChunk 234 labels= ['Knowledge'] ... (parent)")
    print("  (children KnowledgeChunk with their text)")
    print("Upload node (if present): text len = 12345")
    print("Conclusion: If you see text len>0 with experiment_id match, the data is there; UI should surface via chunks.")
    print("If 0 or missing, either no ingest run, or data was deleted by source_file (see hardened delete).")

# For manual inspection: python -c "from testscripts... import simulate...; simulate..."

