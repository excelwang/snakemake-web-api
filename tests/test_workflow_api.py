import pytest
from fastapi.testclient import TestClient
import os
import tempfile
import shutil
from pathlib import Path
import yaml
import time
from unittest.mock import patch

from snakemake_mcp_server.api.main import create_native_fastapi_app
from snakemake_mcp_server.schemas import UserWorkflowRequest

@pytest.fixture(scope="module")
def setup_test_environment():
    """Sets up a temporary snakebase with a test workflow for the API tests."""
    # Use a temporary directory for everything
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # We will mock Path.home() to return this temp directory
        # This way, all code using Path.home() / ".swa" will use our temp dir
        mock_home = temp_path / "fake_home"
        mock_home.mkdir()
        
        snakebase_dir = temp_path / "snakebase"
        wrappers_dir = snakebase_dir / "snakemake-wrappers"
        workflows_dir = snakebase_dir / "snakemake-workflows"
        wrappers_dir.mkdir(parents=True)
        
        # Create a dummy test workflow
        workflow_name = "api_test_workflow"
        workflow_path = workflows_dir / workflow_name
        workflow_path.mkdir(parents=True)

        # 1. Create workflow/Snakefile
        (workflow_path / "workflow").mkdir()
        (workflow_path / "workflow" / "Snakefile").write_text(
            """
rule create_output:
    output: "results/output.txt"
    params:
        message=config["message"]
    threads: config.get("threads", 1)
    shell: "echo {params.message} > {output}"
            """
        )

        # 2. Create config/config.yaml
        (workflow_path / "config").mkdir()
        (workflow_path / "config" / "config.yaml").write_text(
            yaml.dump({"message": "default api message", "threads": 2})
        )

        # 3. Create meta.yaml for info and schema
        (workflow_path / "meta.yaml").write_text(
            yaml.dump({
                "info": {
                    "name": "API Test Workflow",
                    "description": "A workflow for testing the API."
                },
                "params_schema": {
                    "message": {"description": "The message to write to the output file."}
                }
            })
        )

        # 4. Create demos/ directory
        (workflow_path / "demos").mkdir()
        (workflow_path / "demos" / "demo1.yaml").write_text(
            yaml.dump({
                "__description__": "A simple demo case.",
                "message": "hello from demo1"
            })
        )
        
        # Create results dir
        (workflow_path / "results").mkdir()

        # Yield everything needed
        yield {
            "wrappers_path": str(wrappers_dir),
            "workflows_path": str(workflows_dir),
            "mock_home": mock_home
        }


@pytest.fixture(scope="module")
def api_client(setup_test_environment):
    """Create a TestClient for the FastAPI app with the test environment."""
    env = setup_test_environment
    
    # We use multiple patches to ensure total isolation
    with patch("pathlib.Path.home", return_value=env["mock_home"]):
        # Also need to patch it in all modules that might have already imported it or use it
        # Actually, if they use Path.home() call, the patch above is enough.
        
        # Now run the parser to populate our fake home
        from snakemake_mcp_server.cli.parse import parse as parse_command
        from click.testing import CliRunner
        
        runner = CliRunner()
        class MockContext:
            obj = {'WRAPPERS_PATH': env["wrappers_path"], 'WORKFLOWS_DIR': env["workflows_path"]}
        
        result = runner.invoke(parse_command, [], obj=MockContext().obj)
        assert result.exit_code == 0, f"Parser command failed: {result.output}"

        app = create_native_fastapi_app(env["wrappers_path"], env["workflows_path"])
        # We must keep the patch active while using the client because routes call Path.home()
        with TestClient(app) as client:
            yield client


def test_list_workflows(api_client):
    """Test the GET /workflows endpoint."""
    response = api_client.get("/workflows")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["id"] == "api_test_workflow"


def test_get_workflow_meta(api_client):
    """Test the GET /workflows/{workflow_name:path} endpoint."""
    response = api_client.get("/workflows/api_test_workflow")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "api_test_workflow"
    assert data["info"]["name"] == "API Test Workflow"
    assert data["default_config"]["message"] == "default api message"
    assert data["params_schema"]["message"]["description"] is not None


def test_get_workflow_demos(api_client):
    """Test the GET /workflows/demos/{workflow_id:path} endpoint."""
    response = api_client.get("/workflows/demos/api_test_workflow")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "demo1"
    assert data[0]["config"]["message"] == "hello from demo1"


def test_workflow_process_async(api_client):
    """Test the full async lifecycle of the POST /workflow-processes endpoint."""
    # 1. Submit the job with a config override
    request_payload = {
        "workflow_id": "api_test_workflow",
        "config": {"message": "hello async"},
        "target_rule": "results/output.txt"
    }
    response = api_client.post("/workflow-processes", json=request_payload)
    assert response.status_code == 202, f"Submission failed: {response.text}"
    submission_data = response.json()
    job_id = submission_data["job_id"]
    status_url = submission_data["status_url"]
    assert status_url == f"/workflow-processes/{job_id}"

    # 2. Poll for status
    job_status = None
    final_data = {}
    for _ in range(20): # Poll for up to 20 seconds
        time.sleep(1)
        status_response = api_client.get(status_url)
        assert status_response.status_code == 200
        final_data = status_response.json()
        job_status = final_data["status"]
        if job_status in ["completed", "failed"]:
            break
    
    # 3. Assert final status and result
    assert job_status == "completed", f"Job did not complete. Final data: {final_data}"
    assert final_data["result"]["status"] == "success"

    # 4. Verify output file content
    # Snakemake outputs shell commands to stderr by default when using --printshellcmds
    combined_output = final_data["result"]["stdout"] + final_data["result"]["stderr"]
    assert "echo hello async > results/output.txt" in combined_output
