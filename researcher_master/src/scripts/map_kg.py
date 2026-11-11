"""Script to run the KG->chunk mapper and save mapping to ./data/kg_mapping.json
"""
from src.kg.mapper import map_kg_to_chunks


def main():
    mapping = map_kg_to_chunks()
    print(f"Generated mapping for {len(mapping)} KG nodes")


if __name__ == '__main__':
    main()
