import pytest
import os
import shutil
import tempfile
import pytest
import os
import tempfile
import shutil
from pathlib import Path
from snakemake_mcp_server.wrapper_runner import run_wrapper

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

def create_dummy_wrapper(tmpdir: Path, wrapper_name: str, content: str):
    wrapper_path = tmpdir / "bio" / wrapper_name
    wrapper_path.mkdir(parents=True, exist_ok=True)
    (wrapper_path / "Snakefile").write_text(content)
    return str(wrapper_path)




@pytest.fixture
def self_contained_faidx_data():
    """Fixture for a self-contained samtools/faidx test using a temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        input_file = os.path.join(temp_dir, "genome.fasta")
        output_file = os.path.join(temp_dir, "genome.fasta.fai")
        with open(input_file, "w") as f:
            f.write(">chr1\nACGTACGT\n")
        yield input_file, output_file
        # Cleanup is handled by TemporaryDirectory

@pytest.fixture
def arriba_data(wrappers_path):
    """Fixture for the arriba test, using its local data."""
    # Ensure output directory exists
    output_fusions_dir = os.path.join(wrappers_path, "bio/arriba/test/fusions")
    os.makedirs(output_fusions_dir, exist_ok=True)

    output_fusions = os.path.join(output_fusions_dir, "A.fusions.tsv")
    output_discarded = os.path.join(output_fusions_dir, "A.discarded.tsv")
    
    yield output_fusions, output_discarded
    # Teardown
    for f in [output_fusions, output_discarded]:
        if os.path.exists(f):
            os.remove(f)

# --- Test Case Definitions ---

@pytest.mark.asyncio
async def test_samtools_faidx_self_contained(self_contained_faidx_data, wrappers_path):
    """Test samtools/faidx with self-created data in a temp folder."""
    input_file, output_file = self_contained_faidx_data
    
    result = await run_wrapper(
        wrapper_name="bio/samtools/faidx",
        inputs=[input_file],
        outputs=[output_file],
        wrappers_path=wrappers_path,
        workdir=os.path.dirname(input_file), # Pass workdir explicitly
        conda_env=os.path.join(wrappers_path, "bio/samtools/faidx/environment.yaml")
    )
    
    assert result["status"] == "success"
    assert result["exit_code"] == 0
    assert os.path.exists(output_file)

@pytest.mark.asyncio
async def test_arriba_local_data(arriba_data, wrappers_path):
    """Test the arriba wrapper using its existing local test data."""
    fusions_file, discarded_file = arriba_data
    
    result = await run_wrapper(
        wrapper_name="bio/arriba",
        inputs={
            "bam": os.path.join(wrappers_path, "bio/arriba/test/A.bam"),
            "genome": os.path.join(wrappers_path, "bio/arriba/test/genome.fasta"),
            "annotation": os.path.join(wrappers_path, "bio/arriba/test/annotation.gtf")
        },
        outputs={
            "fusions": fusions_file,
            "discarded": discarded_file
        },
        params={
            "genome_build": "GRCh37",
            "extra": f"-d {os.path.join(wrappers_path, 'bio/arriba/test/blacklist.tsv')}"
        },
        threads=2,
        wrappers_path=wrappers_path,
        workdir=os.path.dirname(fusions_file), # Pass workdir explicitly
        conda_env=os.path.join(wrappers_path, "bio/arriba/environment.yaml")
    )
    
    assert result["status"] == "success"
    assert result["exit_code"] == 0
    assert os.path.exists(fusions_file)