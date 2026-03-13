import unicodedata
import re
from typing import Set
import logging

logger = logging.getLogger(__name__)


def canonicalize_concept_id(raw: str) -> str:
    """
    Canonicalize a concept name to a concept ID.

    Rules (from REBUILD-03):
    - Lowercase
    - Unicode normalize (NFKC)
    - Replace spaces, hyphens, punctuation with underscores
    - Collapse repeated underscores
    - Strip leading/trailing underscores
    - Truncate to 100 characters

    Examples:
        "Heat Transfer Coefficient" → "heat_transfer_coefficient"
        "Navier–Stokes Equations" → "navier_stokes_equations"
    """
    if not raw:
        return ""

    # Normalize unicode (NFKD to decompose accented chars, then strip combining marks)
    text = unicodedata.normalize("NFKD", raw)
    # Remove combining characters (accents)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Lowercase
    text = text.lower()
    # Replace non-alphanumeric with underscore
    text = re.sub(r"[^a-z0-9]+", "_", text)
    # Collapse repeated underscores
    text = re.sub(r"_+", "_", text)
    # Strip leading/trailing
    text = text.strip("_")
    # Truncate
    return text[:100]


class ConceptIdRegistry:
    """
    Registry for tracking concept ID collisions during ingestion.
    """

    def __init__(self):
        self._id_to_raw_names: dict[str, Set[str]] = {}

    def register(self, raw_name: str) -> str:
        """
        Register a raw concept name and return its canonical ID.
        Logs a warning if collision is detected.
        """
        canonical_id = canonicalize_concept_id(raw_name)
        if not canonical_id:
            return ""

        if canonical_id not in self._id_to_raw_names:
            self._id_to_raw_names[canonical_id] = set()

        self._id_to_raw_names[canonical_id].add(raw_name)

        # Check for collision
        if len(self._id_to_raw_names[canonical_id]) > 1:
            logger.warning(
                f"Concept ID collision detected: '{canonical_id}' maps to multiple raw names: "
                f"{self._id_to_raw_names[canonical_id]}"
            )

        return canonical_id

    def get_raw_names(self, canonical_id: str) -> Set[str]:
        """Get all raw names that map to a canonical ID."""
        return self._id_to_raw_names.get(canonical_id, set())

    def has_collision(self, canonical_id: str) -> bool:
        """Check if a canonical ID has multiple raw names."""
        return len(self._id_to_raw_names.get(canonical_id, set())) > 1

    def get_collisions(self) -> dict[str, Set[str]]:
        """Get all collisions (IDs with multiple raw names)."""
        return {
            cid: names for cid, names in self._id_to_raw_names.items() if len(names) > 1
        }
