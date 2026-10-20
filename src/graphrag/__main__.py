"""Package entry point: ``python -m src.graphrag`` builds the knowledge graph.

Kept separate from ``builder.py`` so that running the module does not re-import the
package ``__init__`` (which would emit a runpy warning about a double import).
"""
from __future__ import annotations

from .builder import main

if __name__ == "__main__":
    main()
