"""Entry point: python -m src.app.build_index"""

from .ingest import build_index


def main() -> int:
    """Build the vector index. Returns number of chunks indexed."""
    return build_index()


if __name__ == "__main__":
    n = main()
    print(f"Index built: {n} chunks" if n is not None else "Index built.")
