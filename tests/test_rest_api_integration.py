import pytest
import asyncio
import os
from fastapi.testclient import TestClient
from snakemake_mcp_server.api.main import create_native_fastapi_app
import tempfile
import time
from pathlib import Path
import shutil
from snakemake_mcp_server.schemas import UserWrapperRequest, InternalWrapperRequest, PlatformRunParams


@pytest.fixture
def rest_client():
    """Create a TestClient for the FastAPI application."""
    snakebase_dir_env = os.environ.get("SNAKEBASE_DIR")
    if not snakebase_dir_env:
        pytest.fail("SNAKEBASE_DIR environment variable not set.")
    snakebase_dir = Path(snakebase_dir_env).resolve()
    wrappers_path = str(snakebase_dir / "snakemake-wrappers")
    workflows_dir = str(snakebase_dir / "snakemake-workflows")
    
    app = create_native_fastapi_app(wrappers_path, workflows_dir)
    return TestClient(app)


@pytest.mark.asyncio
async def test_direct_fastapi_wrapper_execution(rest_client):
    """Test direct FastAPI wrapper execution."""
    # Test wrapper execution using direct FastAPI access
    response = rest_client.post("/tool-processes", json={
        "wrapper_id": "bio/fastqc",
        "inputs": ["test.fastq"],
        "outputs": ["test_fastqc.html", "test_fastqc.zip"],
        "threads": 1 # Required by InternalWrapperRequest
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
    test_tool_path = "bio/snpsift/varType"
    response = rest_client.get(f"/tools/{test_tool_path}")
    
    assert response.status_code == 200
    result = response.json()
    assert result["info"]["name"] == "SnpSift varType"
    print(f"Direct FastAPI metadata for {test_tool_path}: {result['info']['name']}")
    
    # Demos are no longer in WrapperMetadataResponse, they are fetched from /demos/{wrapper_id}
    # This assertion is now irrelevant for WrapperMetadataResponse
    # if "demos" in result and result["demos"]:
    #     demo = result["demos"][0]
    #     assert "method" in demo
    #     assert "endpoint" in demo
    #     assert "payload" in demo
    #     print(f"Direct FastAPI demo call structure validated for {test_tool_path}")


@pytest.mark.asyncio
async def test_direct_fastapi_demo_structure_validation(rest_client):
    """Test that demo calls are correctly structured with API parameters."""
    test_tool_path = "bio/snpsift/varType"
    
    # Fetch demos from the /demos/{wrapper_id} endpoint
    response = rest_client.get(f"/demos/{test_tool_path}")
    assert response.status_code == 200
    
    demos = response.json()
    assert len(demos) > 0, f"Expected demos for {test_tool_path}, but got none"
    
    # Validate first demo
    demo = demos[0]
    assert "method" in demo
    assert "endpoint" in demo
    assert "payload" in demo
    
    # Validate the payload structure
    payload = demo["payload"]
    assert payload is not None
    assert "wrapper_id" in payload # Ensure wrapper_id is in payload
    
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
    assert demo_case_response["payload"]["wrapper_id"] == "bio/snpsift/varType" # Changed to snpsift/varType
    
    print("\nDirect FastAPI /demo-case endpoint validated for structure.")

    # 2. Extract payload and prepare for execution
    payload = demo_case_response["payload"]
    
    # The workdir and input file are created by the /tool-processes endpoint.
    # We will get the actual workdir and output file path from the job result.
    input_file_name = payload["inputs"]["vcf"]
    output_file_name = payload["outputs"]["vcf"]

    try:
        # 3. Submit the job using the extracted payload
        # The payload from demo_case_response is a UserWrapperRequest,
        # but /tool-processes expects InternalWrapperRequest.
        # We need to construct a valid InternalWrapperRequest.
        internal_payload = InternalWrapperRequest(
            wrapper_id=payload["wrapper_id"],
            inputs=payload.get("inputs"),
            outputs=payload.get("outputs"),
            params=payload.get("params"),
            workdir=".", # Placeholder, actual workdir will be managed by server
            threads=1 # Minimal platform param required
        )

        submit_response = rest_client.post(demo_case_response["endpoint"], json=internal_payload.model_dump(mode="json"))
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
async def test_snpsift_vartype_wrapper_full_flow(rest_client):
    """
    End-to-end test for running the 'bio/snpsift/varType' wrapper through the
    /tool-processes endpoint, verifying job status and output file creation.
    This test now relies on the /tool-processes endpoint to create dummy input files.
    """
    # Construct the UserSnakemakeWrapperRequest payload
    # /tool-processes expects an InternalWrapperRequest
    wrapper_id = "bio/snpsift/varType"
    temp_dir = Path(tempfile.mkdtemp())
    
    internal_payload = InternalWrapperRequest(
        wrapper_id=wrapper_id,
        inputs={"vcf": "in.vcf"},
        outputs={"vcf": "annotated/out.vcf"},
        workdir=str(temp_dir), # Pass a temporary workdir
        threads=1 # Minimal platform param required
    )

    # Submit the job
    response = rest_client.post("/tool-processes", json=internal_payload.model_dump(mode="json"))
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
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        print(f"Cleaned up temporary directory: {temp_dir}")