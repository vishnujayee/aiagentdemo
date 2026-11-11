"""Convenience script to run the full local pipeline:
1) ingest seed Wikipedia pages
2) build a lightweight KG from the indexed chunks
3) map KG nodes to retrieved chunks (provenance)

Usage:
    python -m src.scripts.run_pipeline
"""
from src.scripts.ingest_wiki import main as ingest_main
from src.scripts.build_kg import main as build_kg_main
from src.kg.mapper import map_kg_to_chunks


def main():
    print("1) Ingesting seed Wikipedia pages into the retriever...")
    ingest_main()
    print("2) Building knowledge graph from indexed chunks...")
    build_kg_main()
    print("3) Mapping KG nodes to chunks (provenance)...")
    m = map_kg_to_chunks()
    print(f"Mapped {len(m)} KG nodes. Written to ./data/kg_mapping.json")


if __name__ == '__main__':
    main()
