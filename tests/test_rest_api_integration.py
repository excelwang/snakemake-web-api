"""
Integration tests for direct FastAPI REST endpoints.

These tests verify the native FastAPI functionality without MCP wrapper.
"""
import pytest
import asyncio
from fastapi.testclient import TestClient
from snakemake_mcp_server.fastapi_app import create_native_fastapi_app
import tempfile
import time
from pathlib import Path


@pytest.fixture
def rest_client():
    """Create a TestClient for the FastAPI application directly."""
    # Use the default paths for the test environment
    app = create_native_fastapi_app("./snakebase/snakemake-wrappers", "./snakebase/workflows")
    return TestClient(app)


@pytest.mark.asyncio
async def test_direct_fastapi_workflow_execution(rest_client):
    """Test direct FastAPI workflow execution."""
    # Test workflow execution using direct FastAPI access
    response = rest_client.post("/workflow-processes", json={
        "workflow_name": "hello",
        "inputs": {"name": "test"},
        "outputs": ["hello.txt"],
        "params": {"greeting": "Hello"}
    })
    
    assert response.status_code in [200, 202, 422]  # 422 is expected if files don't exist


@pytest.mark.asyncio
async def test_direct_fastapi_wrapper_execution(rest_client):
    """Test direct FastAPI wrapper execution."""
    # Test wrapper execution using direct FastAPI access
    response = rest_client.post("/tool-processes", json={
        "wrapper_name": "bio/fastqc",
        "inputs": ["test.fastq"],
        "outputs": ["test_fastqc.html", "test_fastqc.zip"],
        "params": {"dir": "/tmp"}
    })
    
    assert response.status_code in [200, 202, 422]  # 422 is expected if files don't exist


@pytest.mark.asyncio
async def test_direct_fastapi_wrapper_list(rest_client):
    """Test direct FastAPI wrapper listing."""
    response = rest_client.get("/tools")
    
    assert response.status_code == 200
    result = response.json()
    assert "wrappers" in result
    assert "total_count" in result
    print(f"Direct FastAPI found {result['total_count']} wrappers")


@pytest.mark.asyncio
async def test_direct_fastapi_wrapper_metadata(rest_client):
    """Test direct FastAPI wrapper metadata retrieval."""
    # First get available tools to pick a valid one
    response = rest_client.get("/tools")
    assert response.status_code == 200
    result = response.json()
    
    wrappers = result.get("wrappers", [])
    if not wrappers:
        pytest.skip("No wrappers available for testing")
        
    # Use the first available wrapper
    test_wrapper = wrappers[0]
    test_tool_path = test_wrapper.get("path", "")
    
    if not test_tool_path:
        pytest.skip("No valid tool path found")
        
    response = rest_client.get(f"/tools/{test_tool_path}")
    
    assert response.status_code == 200
    result = response.json()
    assert "name" in result
    print(f"Direct FastAPI metadata for {test_tool_path}: {result['name']}")
    
    # Verify demo calls are included
    if "demos" in result and result["demos"]:
        demo = result["demos"][0]
        assert "method" in demo
        assert "endpoint" in demo
        assert "payload" in demo
        print(f"Direct FastAPI demo call structure validated for {test_tool_path}")


@pytest.mark.asyncio
async def test_direct_fastapi_demo_structure_validation(rest_client):
    """Test that demo calls are correctly structured with API parameters."""
    # First get available tools to pick a valid one
    response = rest_client.get("/tools")
    assert response.status_code == 200
    result = response.json()
    
    wrappers = result.get("wrappers", [])
    if not wrappers:
        pytest.skip("No wrappers available for testing demo structure")
    
    # Use the first available wrapper
    test_wrapper = wrappers[0]
    test_tool_path = test_wrapper.get("path", "")
    
    if not test_tool_path:
        pytest.skip("No valid tool path found for demo testing")
    
    response = rest_client.get(f"/tools/{test_tool_path}")
    assert response.status_code == 200
    
    result = response.json()
    demos = result.get("demos", [])
    assert len(demos) > 0, f"Expected demos for {test_tool_path}, but got none"
    
    # Validate first demo
    demo = demos[0]
    assert "method" in demo
    assert "endpoint" in demo
    assert "payload" in demo
    
    # Validate the payload structure
    payload = demo["payload"]
    assert payload is not None
    
    pass


@pytest.mark.asyncio
async def test_direct_fastapi_demo_case_endpoint(rest_client):
    """Test the /demo-case endpoint to ensure it returns the expected structure."""
    response = rest_client.get("/demo-case")
    
    assert response.status_code == 200
    result = response.json()
    
    assert "method" in result
    assert "endpoint" in result
    assert "payload" in result
    assert "curl_example" in result
    
    assert result["method"] == "POST"
    assert result["endpoint"] == "/tool-processes"
    assert result["payload"]["wrapper_name"] == "bio/samtools/faidx"
    
    print("Direct FastAPI /demo-case endpoint validated.")


@pytest.mark.asyncio
async def test_samtools_faidx_wrapper_full_flow(rest_client):
    """
    End-to-end test for running the 'bio/samtools/faidx' wrapper through the
    /tool-processes endpoint, verifying job status and output file creation.
    """
    # Use the wrappers_path from the fixture setup, which is "./snakebase"
    wrappers_path = "./snakebase/snakemake-wrappers" # This is passed to create_native_fastapi_app, so it's the base for conda_env

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        input_file_name = "genome.fasta"
        output_file_name = "genome.fasta.fai"
        
        input_file_full_path = tmp_path / input_file_name
        output_file_full_path = tmp_path / output_file_name

        # Create dummy input file
        input_file_full_path.write_text(">chr1\nACGTACGT\n>chr2\nTGCA\n")

        # Construct the SnakemakeWrapperRequest payload
        # inputs and outputs are relative to the 'workdir'
        # The wrapper_name should be relative to the wrappers_path
        payload = {
            "wrapper_name": "bio/samtools/faidx",
            "inputs": [input_file_name],
            "outputs": [output_file_name],
            "workdir": str(tmp_path), # Pass the absolute path of the temporary directory as workdir
            "conda_env": "/root/snakemake-mcp-server/snakebase/snakemake-wrappers/bio/samtools/faidx/environment.yaml"
        }

        # Submit the job
        response = rest_client.post("/tool-processes", json=payload)
        assert response.status_code == 202
        submission_response = response.json()
        job_id = submission_response["job_id"]
        status_url = submission_response["status_url"]

        print(f"\nSubmitted job ID: {job_id}")
        print(f"Status URL: {status_url}")

        # Poll job status
        max_attempts = 60
        attempts = 0
        job_status = None
        while attempts < max_attempts:
            time.sleep(1) # Wait for 1 second before polling again
            status_response = rest_client.get(status_url)
            assert status_response.status_code == 200
            job_status_data = status_response.json()
            job_status = job_status_data["status"]

            print(f"Polling job {job_id}, status: {job_status}")

            if job_status in ["completed", "failed"]:
                break
            attempts += 1
        
        assert job_status == "completed", f"Job failed or timed out. Final status: {job_status}, Result: {job_status_data.get('result')}"

        # Verify output file
        # Give a small delay to ensure file system is updated
        time.sleep(2)
        assert output_file_full_path.exists(), f"Output file {output_file_full_path} was not created."
        assert output_file_full_path.read_text() == "chr1\t8\t6\t8\t9\nchr2\t4\t21\t4\t5\n"
        print(f"Output file {output_file_full_path} verified.")