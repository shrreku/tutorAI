import pytest
from app.utils.canonicalization import canonicalize_concept_id, ConceptIdRegistry


class TestCanonicalizeConcept:
    """Tests for concept ID canonicalization."""
    
    def test_basic_canonicalization(self):
        """Test basic string canonicalization."""
        assert canonicalize_concept_id("Heat Transfer Coefficient") == "heat_transfer_coefficient"
        assert canonicalize_concept_id("Navier–Stokes Equations") == "navier_stokes_equations"
    
    def test_unicode_normalization(self):
        """Test unicode characters are normalized."""
        # Em dash and en dash should become underscore
        assert canonicalize_concept_id("A–B—C") == "a_b_c"
        # Accented characters
        assert canonicalize_concept_id("café") == "cafe"
    
    def test_special_characters(self):
        """Test special characters are replaced."""
        assert canonicalize_concept_id("foo-bar") == "foo_bar"
        assert canonicalize_concept_id("foo.bar") == "foo_bar"
        assert canonicalize_concept_id("foo/bar") == "foo_bar"
        assert canonicalize_concept_id("foo (bar)") == "foo_bar"
    
    def test_collapse_underscores(self):
        """Test repeated underscores are collapsed."""
        assert canonicalize_concept_id("foo   bar") == "foo_bar"
        assert canonicalize_concept_id("foo___bar") == "foo_bar"
        assert canonicalize_concept_id("foo - bar") == "foo_bar"
    
    def test_strip_underscores(self):
        """Test leading/trailing underscores are stripped."""
        assert canonicalize_concept_id("  foo  ") == "foo"
        assert canonicalize_concept_id("_foo_") == "foo"
        assert canonicalize_concept_id("__foo__") == "foo"
    
    def test_truncation(self):
        """Test long strings are truncated."""
        long_name = "a" * 150
        result = canonicalize_concept_id(long_name)
        assert len(result) == 100
    
    def test_empty_string(self):
        """Test empty string returns empty."""
        assert canonicalize_concept_id("") == ""
        assert canonicalize_concept_id("   ") == ""
    
    def test_numbers_preserved(self):
        """Test numbers are preserved."""
        assert canonicalize_concept_id("Chapter 1") == "chapter_1"
        assert canonicalize_concept_id("2nd Law") == "2nd_law"


class TestConceptIdRegistry:
    """Tests for concept ID collision detection."""
    
    def test_register_returns_canonical_id(self):
        """Test registering returns canonical ID."""
        registry = ConceptIdRegistry()
        cid = registry.register("Heat Transfer")
        assert cid == "heat_transfer"
    
    def test_collision_detection(self):
        """Test collision is detected when two names map to same ID."""
        registry = ConceptIdRegistry()
        registry.register("Heat Transfer")
        registry.register("heat-transfer")  # Different raw, same canonical
        
        assert registry.has_collision("heat_transfer")
        assert registry.get_raw_names("heat_transfer") == {"Heat Transfer", "heat-transfer"}
    
    def test_no_collision_for_same_raw(self):
        """Test no collision for same raw name registered twice."""
        registry = ConceptIdRegistry()
        registry.register("Heat Transfer")
        registry.register("Heat Transfer")
        
        assert not registry.has_collision("heat_transfer")
    
    def test_get_collisions(self):
        """Test getting all collisions."""
        registry = ConceptIdRegistry()
        registry.register("Heat Transfer")
        registry.register("heat-transfer")
        registry.register("Mass Transfer")
        
        collisions = registry.get_collisions()
        assert "heat_transfer" in collisions
        assert "mass_transfer" not in collisions
