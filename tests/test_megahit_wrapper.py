import pytest
import asyncio
import os
import tempfile
import gzip
from fastmcp import Client

@pytest.mark.asyncio
async def test_megahit_wrapper(http_client: Client, wrappers_path):
    """Test the megahit wrapper with container, benchmark, resources, and shadow."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create dummy input files
        r1_path = os.path.join(temp_dir, "sample1_R1.fastq.gz")
        r2_path = os.path.join(temp_dir, "sample1_R2.fastq.gz")
        
        with gzip.open(r1_path, "wt") as f:
            f.write("@read1\nAGCT\n+\nIIII\n")
        with gzip.open(r2_path, "wt") as f:
            f.write("@read1\nAGCT\n+\nIIII\n")

        output_dir = os.path.join(temp_dir, "assembly")
        os.makedirs(output_dir)
        output_file = os.path.join(output_dir, "final.contigs.fasta")
        benchmark_file = os.path.join(temp_dir, "benchmark.txt")

        result = await http_client.call_tool(
            "run_snakemake_wrapper",
            {
                "wrapper_name": "megahit",
                "inputs": {
                    "reads": [r1_path, r2_path]
                },
                "outputs": {"contigs": output_file},
                "params": {"extra": "--min-count 10 --k-list 21,29,39,59,79,99,119,141"},
                "container": "docker://continuumio/miniconda3:4.4.10",
                "benchmark": benchmark_file,
                "resources": {"mem_mb": 250000},
            },
        )

        assert result.data["status"] == "success"
        assert result.data["exit_code"] == 0
        assert os.path.exists(output_file)
        assert os.path.exists(benchmark_file)
