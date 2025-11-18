import os
import tempfile
import shutil
from pathlib import Path
import pytest
from snakemake_mcp_server.snakefile_parser import generate_demo_calls_for_wrapper

@pytest.fixture
def snakemake_wrapper_test_dir():
    """Creates a temporary directory structure for a snakemake wrapper test."""
    temp_dir = tempfile.mkdtemp()
    
    # This is the root for all wrappers
    wrappers_root = Path(temp_dir)
    
    # This is the specific wrapper directory
    wrapper_path = wrappers_root / "bio" / "test-wrapper"
    
    # This is the test directory within the wrapper
    test_dir = wrapper_path / "test"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a dummy meta.yaml
    with open(wrapper_path / "meta.yaml", "w") as f:
        f.write("name: test-wrapper\ndescription: A test wrapper.")
        
    # Create dummy input files
    with open(test_dir / "file1.fa", "w") as f:
        f.write(">seq1\nACGT")
    with open(test_dir / "file2.vcf", "w") as f:
        f.write("##fileformat=VCFv4.2")
    with open(test_dir / "track1.bam", "w") as f:
        f.write("BAM_CONTENT")
        
    yield str(wrapper_path), str(wrappers_root)
    
    shutil.rmtree(temp_dir)

def test_parser_preserves_list_in_input(snakemake_wrapper_test_dir):
    """
    Tests that the snakefile parser correctly identifies a list in the input
    directive and preserves it as a list, not a string.
    """
    wrapper_path, wrappers_root = snakemake_wrapper_test_dir
    test_dir = Path(wrapper_path) / "test"
    
    # Create the Snakefile that mimics the igv-reports case
    snakefile_content = """
rule test_rule:
    input:
        fasta="file1.fa",
        vcf="file2.vcf",
        tracks=["track1.bam"]
    output:
        "report.html"
    wrapper:
        "bio/test-wrapper"
"""
    with open(test_dir / "Snakefile", "w") as f:
        f.write(snakefile_content)
        
    # Run the parser function
    demo_calls = generate_demo_calls_for_wrapper(wrapper_path, wrappers_root)
    
    # --- Assertions ---
    # 1. We should get exactly one demo call
    assert len(demo_calls) == 1, "Expected to find exactly one demo call."
    
    # 2. The 'input' key should exist
    demo_input = demo_calls[0].get("input")
    assert demo_input is not None, "The 'input' key is missing from the demo payload."
    
    # 3. The 'tracks' key should exist in the input dict
    tracks_value = demo_input.get("tracks")
    assert tracks_value is not None, "The 'tracks' key is missing from the input dictionary."
    
    # 4. The value of 'tracks' MUST be a list
    assert isinstance(tracks_value, list), f"Expected 'tracks' to be a list, but it was a {type(tracks_value)}."
    
    # 5. The list should contain the correct filename
    assert tracks_value == ["track1.bam"], f"The 'tracks' list has incorrect content: {tracks_value}"

