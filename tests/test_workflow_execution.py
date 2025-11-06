import pytest
import asyncio
import os
import tempfile
import shutil
from pathlib import Path
from fastmcp import Client
import yaml

# Import the SnakemakeResponse model to check type
from snakemake_mcp_server.fastapi_app import SnakemakeResponse

@pytest.fixture(scope="function")
def dummy_workflow_setup(workflows_dir):
    """Sets up a dummy Snakemake workflow for testing."""
    # Create a temporary directory for the dummy workflow within workflows_dir
    workflow_name = "dummy_test_workflow"
    dummy_workflow_path = Path(workflows_dir) / workflow_name
    dummy_workflow_path.mkdir(parents=True, exist_ok=True)

    # Create workflow/Snakefile
    workflow_snakefile_dir = dummy_workflow_path / "workflow"
    workflow_snakefile_dir.mkdir()
    workflow_snakefile = workflow_snakefile_dir / "Snakefile"
    
    snakefile_content = """
rule all:
    input: "results/output.txt"

rule create_output:
    output: "results/output.txt"
    params:
        message = config["message"]
    shell:
        "echo {params.message} > {output}"
"""
    workflow_snakefile.write_text(snakefile_content)

    # Create config/config.yaml
    config_dir = dummy_workflow_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    
    config_content = {"message": "default message"}
    with open(config_file, 'w') as f:
        yaml.dump(config_content, f)

    # Create results directory
    results_dir = dummy_workflow_path / "results"
    results_dir.mkdir()

    yield {
        "workflow_name": workflow_name,
        "workflow_path": str(dummy_workflow_path),
        "output_file": str(results_dir / "output.txt"),
        "config_file": str(config_file),
    }

    # Teardown: Clean up the dummy workflow directory
    try:
        shutil.rmtree(dummy_workflow_path)
    except Exception as e:
        print(f"Warning: Failed to clean up dummy workflow {dummy_workflow_path}: {e}")

@pytest.mark.asyncio
async def test_run_snakemake_workflow_basic(http_client: Client, dummy_workflow_setup):
    """测试 run_snakemake_workflow 的基本功能"""
    workflow_name = dummy_workflow_setup["workflow_name"]
    output_file = dummy_workflow_setup["output_file"]

    result = await asyncio.wait_for(
        http_client.call_tool(
            "run_snakemake_workflow",
            {
                "workflow_name": workflow_name,
                "outputs": [output_file], # Specify output to trigger the rule
            }
        ),
        timeout=120 # Workflow execution might take time
    )

    # The new FastAPI-first approach returns a structured SnakemakeResponse model
    # Determine the correct access method based on the type
    if hasattr(result.data, 'status'):  # If it's the new SnakemakeResponse model
        status = result.data.status
    else:
        # For backward compatibility if it's still a dict
        status = result.data.get('status') if isinstance(result.data, dict) else getattr(result.data, 'status', None)
    
    assert status == 'success'
    assert os.path.exists(output_file)
    with open(output_file, 'r') as f:
        content = f.read().strip()
        assert content == "default message"

@pytest.mark.asyncio
async def test_run_snakemake_workflow_with_params(http_client: Client, dummy_workflow_setup):
    """测试 run_snakemake_workflow 传递参数并修改配置"""
    workflow_name = dummy_workflow_setup["workflow_name"]
    output_file = dummy_workflow_setup["output_file"]
    
    new_message = "hello from params"

    result = await asyncio.wait_for(
        http_client.call_tool(
            "run_snakemake_workflow",
            {
                "workflow_name": workflow_name,
                "outputs": [output_file],
                "params": {"message": new_message}, # Override message via params
            }
        ),
        timeout=120
    )

    # The new FastAPI-first approach returns a structured SnakemakeResponse model
    # Determine the correct access method based on the type
    if hasattr(result.data, 'status'):  # If it's the new SnakemakeResponse model
        status = result.data.status
    else:
        # For backward compatibility if it's still a dict
        status = result.data.get('status') if isinstance(result.data, dict) else getattr(result.data, 'status', None)
    
    assert status == 'success'
    assert os.path.exists(output_file)
    with open(output_file, 'r') as f:
        content = f.read().strip()
        assert content == new_message

@pytest.mark.asyncio
async def test_lint_snakemake_workflow_template(http_client: Client):
    """Tests linting the snakemake-workflow-template workflow."""
    result = await asyncio.wait_for(
        http_client.call_tool(
            "run_snakemake_workflow",
            {
                "workflow_name": "snakemake-workflow-template",
                "extra_snakemake_args": "--lint",
            }
        ),
        timeout=120
    )

    # The new FastAPI-first approach returns a structured SnakemakeResponse model
    # Determine the correct access method based on the type
    if hasattr(result.data, 'status'):  # If it's the new SnakemakeResponse model
        status = result.data.status
    else:
        # For backward compatibility if it's still a dict
        status = result.data.get('status') if isinstance(result.data, dict) else getattr(result.data, 'status', None)
    
    assert status == 'success'
