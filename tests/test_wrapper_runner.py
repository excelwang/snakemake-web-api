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

@pytest.fixture
def wrappers_path():
    # This fixture should point to the root of the snakemake-wrappers repository
    # For testing purposes, we can use the current working directory if it's the repo root
    # or a specific path if the tests are run from elsewhere.
    # For now, let's assume the test is run from the snakemake-wrappers root or a subfolder
    # and we can find the 'bio' directory relative to it.
    current_dir = Path(__file__).parent.parent.parent # snakemake-mcp-server/tests -> snakemake-mcp-server -> snakemake-wrappers
    return str(current_dir)

def create_dummy_wrapper(tmpdir: Path, wrapper_name: str, content: str):
    wrapper_path = tmpdir / "bio" / wrapper_name
    wrapper_path.mkdir(parents=True, exist_ok=True)
    (wrapper_path / "Snakefile").write_text(content)
    return str(wrapper_path)


def test_samtools_faidx_self_contained(temp_dir, wrappers_path):
    # Create dummy input file
    input_fasta = temp_dir / "test.fasta"
    input_fasta.write_text(">chr1\nATCG\n")

    # Define output file
    output_fai = temp_dir / "test.fasta.fai"

    # Call the wrapper
    result = run_wrapper(
        wrapper_name="samtools/faidx",
        inputs=[str(input_fasta)],
        outputs=[str(output_fai)],
        wrappers_path=wrappers_path,
        threads=1,
    )

    assert result["status"] == "success"
    assert os.path.exists(output_fai)
    assert "chr1\t4\t0\t4\t5" in output_fai.read_text()

def test_arriba_local_data(temp_dir, wrappers_path):
    # Create dummy input files
    input_bam = temp_dir / "test.bam"
    input_bam.write_text("dummy bam content")
    input_bai = temp_dir / "test.bam.bai"
    input_bai.write_text("dummy bai content")
    input_fasta = temp_dir / "test.fasta"
    input_fasta.write_text("dummy fasta content")
    input_gtf = temp_dir / "test.gtf"
    input_gtf.write_text("dummy gtf content")

    # Define output files
    output_fusions = temp_dir / "fusions.tsv"
    output_discarded = temp_dir / "discarded_fusions.tsv"

    # Call the wrapper
    result = run_wrapper(
        wrapper_name="arriba",
        inputs={
            "bam": str(input_bam),
            "bai": str(input_bai),
            "fasta": str(input_fasta),
            "gtf": str(input_gtf),
        },
        outputs=[str(output_fusions), str(output_discarded)],
        wrappers_path=wrappers_path,
        threads=1,
        params={
            "extra": "--some-arriba-param"
        }
    )

    assert result["status"] == "success"
    assert os.path.exists(output_fusions)
    assert os.path.exists(output_discarded)



SNAKEMAKE_WRAPPERS_PATH = os.environ.get("SNAKEMAKE_WRAPPERS_PATH")

@pytest.fixture
def wrappers_path():
    if not SNAKEMAKE_WRAPPERS_PATH:
        pytest.skip("SNAKEMAKE_WRAPPERS_PATH environment variable not set.")
    return SNAKEMAKE_WRAPPERS_PATH

# --- Fixture Definitions ---

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

def test_samtools_faidx_self_contained(self_contained_faidx_data, wrappers_path):
    """Test samtools/faidx with self-created data in a temp folder."""
    input_file, output_file = self_contained_faidx_data
    
    result = run_wrapper(
        wrapper_name="samtools/faidx",
        inputs=[input_file],
        outputs=[output_file],
        wrappers_path=wrappers_path,
    )
    
    assert result["status"] == "success"
    assert result["exit_code"] == 0
    assert os.path.exists(output_file)

def test_arriba_local_data(arriba_data, wrappers_path):
    """Test the arriba wrapper using its existing local test data."""
    fusions_file, discarded_file = arriba_data
    
    result = run_wrapper(
        wrapper_name="arriba",
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
    )
    
    assert result["status"] == "success"
    assert result["exit_code"] == 0
    assert os.path.exists(fusions_file)