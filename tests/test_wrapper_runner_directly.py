import pytest
import os
import shutil
import tempfile
from pathlib import Path

import os
import json
from pathlib import Path
from snakemake_mcp_server.wrapper_runner import run_wrapper
from snakemake_mcp_server.schemas import UserWrapperRequest, PlatformRunParams

SNAKEBASE_DIR_ENV = os.environ.get("SNAKEBASE_DIR")
if not SNAKEBASE_DIR_ENV:
    # We can't use pytest.fail here as it's top-level, 
    # but the tests will fail later if this is missing.
    # Alternatively, use a dummy path.
    SNAKEBASE_DIR = Path("/tmp/missing_snakebase")
else:
    SNAKEBASE_DIR = Path(SNAKEBASE_DIR_ENV).resolve()

WRAPPERS_PATH = SNAKEBASE_DIR / "snakemake-wrappers"

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
def wrappers_path():
    return os.path.join(SNAKEBASE_DIR, "snakemake-wrappers")




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
async def test_samtools_faidx_self_contained(self_contained_faidx_data, run_wrapper_test):
    """Test samtools/faidx with self-created data in a temp folder."""
    wrapper_runner, workdir = run_wrapper_test
    
    # Copy input file to the test work directory
    input_file, output_file = self_contained_faidx_data
    input_filename = os.path.basename(input_file)
    output_filename = os.path.basename(output_file)
    input_path = os.path.join(workdir, input_filename)
    output_path = os.path.join(workdir, output_filename)
    
    shutil.copy2(input_file, input_path)

    result = await wrapper_runner(
        wrapper_id="bio/samtools/faidx",
        inputs=[input_filename],
        outputs=[output_path]
    )

    assert result["status"] == "success"
    assert result["exit_code"] == 0
    assert os.path.exists(output_path)