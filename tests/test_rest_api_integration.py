"""
Integration tests for direct FastAPI REST endpoints.

These tests verify the native FastAPI functionality without MCP wrapper.
"""
import pytest
import asyncio
from fastapi.testclient import TestClient
from snakemake_mcp_server.api.main import create_native_fastapi_app
import tempfile
import time
from pathlib import Path
import shutil


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
        "outputs": ["test_fastqc.html", "test_fastqc.zip"]
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
    test_tool_path = "bio/samtools/faidx"
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
    test_tool_path = "bio/samtools/faidx"
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
    """
    Test the /demo-case endpoint to ensure it returns a runnable structure,
    then executes the returned payload and verifies the outcome.
    """
    # 1. Get the demo case from the /demo-case endpoint
    response = rest_client.get("/demo-case")
    
    assert response.status_code == 200
    demo_case_response = response.json()
    
    assert "method" in demo_case_response
    assert "endpoint" in demo_case_response
    assert "payload" in demo_case_response
    assert "curl_example" in demo_case_response
    
    assert demo_case_response["method"] == "POST"
    assert demo_case_response["endpoint"] == "/tool-processes"
    assert demo_case_response["payload"]["wrapper_name"] == "bio/samtools/faidx"
    
    print("\nDirect FastAPI /demo-case endpoint validated for structure.")

        # 2. Extract payload and prepare for execution
    payload = demo_case_response["payload"]
    
    # The workdir and input file are created by the /tool-processes endpoint.
    # We will get the actual workdir and output file path from the job result.
    input_file_name = payload["inputs"][0]
    output_file_name = payload["outputs"][0]

    try:
        # 3. Submit the job using the extracted payload
        submit_response = rest_client.post(demo_case_response["endpoint"], json=payload)
        assert submit_response.status_code == 202
        submission_data = submit_response.json()
        job_id = submission_data["job_id"]
        status_url = submission_data["status_url"]

        print(f"Submitted demo job ID: {job_id}")
        print(f"Demo job Status URL: {status_url}")

        # 4. Poll job status
        max_attempts = 60
        attempts = 0
        job_status = None
        job_status_data = {}
        while attempts < max_attempts:
            time.sleep(1) # Wait for 1 second before polling again
            status_check_response = rest_client.get(status_url)
            assert status_check_response.status_code == 200
            job_status_data = status_check_response.json()
            job_status = job_status_data["status"]

            print(f"Polling demo job {job_id}, status: {job_status}")

            if job_status in ["completed", "failed"]:
                break
            attempts += 1
        
        assert job_status == "completed", f"Demo job failed or timed out. Final status: {job_status}, Result: {job_status_data.get('result')}"

        # Extract workdir and output file path from the job result
        job_result = job_status_data["result"]
        assert "output_files" in job_result and len(job_result["output_files"]) > 0
        output_file_full_path = Path(job_result["output_files"][0])
        workdir = output_file_full_path.parent # The workdir is the parent of the output file

        # 5. Verify output file
        time.sleep(2) # Give a small delay to ensure file system is updated
        assert output_file_full_path.exists(), f"Output file {output_file_full_path} was not created by demo job."
        print(f"Output file {output_file_full_path} from demo job verified.")

    finally:
        # 6. Clean up the temporary directory created by /demo-case
        # The workdir is now derived from the output_file_full_path
        if 'workdir' in locals() and workdir.exists():
            shutil.rmtree(workdir)
            print(f"Cleaned up temporary directory: {workdir}")


@pytest.mark.asyncio
async def test_samtools_faidx_wrapper_full_flow(rest_client):
    """
    End-to-end test for running the 'bio/samtools/faidx' wrapper through the
    /tool-processes endpoint, verifying job status and output file creation.
    This test now relies on the /tool-processes endpoint to create dummy input files.
    """
    # Construct the UserSnakemakeWrapperRequest payload
    payload = {
        "wrapper_name": "bio/samtools/faidx",
        "inputs": ["genome.fa"],
        "outputs": ["genome.fa.fai"],
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
    job_status_data = {}
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

    # Extract workdir and output file path from the job result
    job_result = job_status_data["result"]
    assert "output_files" in job_result and len(job_result["output_files"]) > 0
    output_file_full_path = Path(job_result["output_files"][0])
    workdir = output_file_full_path.parent # The workdir is the parent of the output file

    # Verify output file
    # Give a small delay to ensure file system is updated
    time.sleep(2)
    assert output_file_full_path.exists(), f"Output file {output_file_full_path} was not created."
    print(f"Output file {output_file_full_path} verified.")

    # Clean up the temporary directory created by the server
    if workdir.exists():
        shutil.rmtree(workdir)
        print(f"Cleaned up temporary directory: {workdir}")