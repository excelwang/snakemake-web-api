import pytest
import os
import tempfile
import gzip

@pytest.mark.asyncio
async def test_megahit_wrapper(run_wrapper_test):
    """Test the megahit wrapper."""
    wrapper_runner, workdir = run_wrapper_test

    # Create dummy input files
    r1_path = os.path.join(workdir, "sample1_R1.fastq.gz")
    r2_path = os.path.join(workdir, "sample1_R2.fastq.gz")

    with gzip.open(r1_path, "wt") as f:
        f.write("@read1\nAGCT\n+\nIIII\n")
    with gzip.open(r2_path, "wt") as f:
        f.write("@read1\nAGCT\n+\nIIII\n")

    output_dir = os.path.join(workdir, "assembly")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join("assembly", "final.contigs.fasta")

    result = await wrapper_runner(
        wrapper_id="bio/megahit",
        inputs={
            "reads": ["sample1_R1.fastq.gz", "sample1_R2.fastq.gz"]
        },
        outputs={"contigs": output_file},
        params={"extra": "--min-count 10 --k-list 21,29,39,59,79,99,119,141"},
    )

    assert result["status"] == "success"
    assert result["exit_code"] == 0
    assert os.path.exists(os.path.join(workdir, output_file))
