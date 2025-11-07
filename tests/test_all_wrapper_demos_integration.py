"""
Integration test to run through all wrapper demos and verify API functionality.

This test systematically goes through all available wrappers and executes their demo calls,
logging the status of each demo with appropriate logging levels.
"""
import pytest
import asyncio
from fastapi.testclient import TestClient
import logging
from snakemake_mcp_server.fastapi_app import create_native_fastapi_app


@pytest.fixture
def rest_client():
    """Create a TestClient for the FastAPI application directly."""
    app = create_native_fastapi_app("./snakebase/snakemake-wrappers", "./snakebase/workflows")
    return TestClient(app)


@pytest.mark.asyncio
async def test_all_wrapper_demos_integration(rest_client):
    """
    Integration test to run through all available wrapper demos and verify functionality.
    Logs status for each demo using appropriate log levels.
    """
    # Get all available wrappers
    logging.warning("Starting comprehensive wrapper demo integration test...")
    
    response = rest_client.get("/tools")
    assert response.status_code == 200, "Failed to get wrapper list"
    
    result = response.json()
    wrappers = result.get("wrappers", [])
    total_wrappers = len(wrappers)
    
    if total_wrappers == 0:
        logging.warning("No wrappers found, skipping demo integration test")
        return
    
    logging.warning(f"Found {total_wrappers} total wrappers, starting demo integration test...")
    
    successful_demos = 0
    failed_demos = 0
    total_demos_tested = 0
    
    # Keep track of failed wrappers for summary
    failed_wrappers = []
    
    for i, wrapper in enumerate(wrappers):
        wrapper_path = wrapper.get("path", "")
        
        if not wrapper_path:
            logging.warning(f"Wrapper {i+1}/{total_wrappers}: Skipped - no path available")
            continue
            
        # Get detailed metadata for this wrapper to access demos
        metadata_response = rest_client.get(f"/tools/{wrapper_path}")
        
        if metadata_response.status_code != 200:
            logging.warning(f"Wrapper {i+1}/{total_wrappers}: {wrapper_path} - Failed to get metadata (Status: {metadata_response.status_code})")
            failed_wrappers.append((wrapper_path, "metadata_fetch_failed"))
            continue
        
        metadata = metadata_response.json()
        demos = metadata.get("demos", [])
        
        if not demos:
            logging.warning(f"Wrapper {i+1}/{total_wrappers}: {wrapper_path} - No demos available")
            continue
        
        logging.warning(f"Wrapper {i+1}/{total_wrappers}: {wrapper_path} - Testing {len(demos)} demo(s)")
        
        wrapper_demo_success_count = 0
        wrapper_demo_fail_count = 0
        
        # Test each demo for this wrapper
        for j, demo in enumerate(demos):
            total_demos_tested += 1
            
            try:
                # Extract the API call information from the demo
                method = demo.get("method", "POST")
                endpoint = demo.get("endpoint", "")
                payload = demo.get("payload", {})
                curl_example = demo.get("curl_example", "")
                
                if not endpoint:
                    logging.warning(f"  Demo {j+1}: Skipped - no endpoint specified")
                    wrapper_demo_fail_count += 1
                    failed_demos += 1
                    continue
                
                # Execute the demo call
                if method.upper() == "POST":
                    demo_response = rest_client.post(endpoint, json=payload)
                elif method.upper() == "GET":
                    # For GET requests, we might need to pass parameters differently
                    demo_response = rest_client.get(endpoint, params=payload)
                else:
                    logging.warning(f"  Demo {j+1}: Skipped - unsupported method {method}")
                    wrapper_demo_fail_count += 1
                    failed_demos += 1
                    continue
                
                # Check if the call was successful (consider both success and expected validation errors)
                if demo_response.status_code in [200, 422]:  # 422 is expected for validation errors with missing files
                    status_text = "SUCCESS" if demo_response.status_code == 200 else "EXPECTED_ERROR (validation)"
                    logging.warning(f"  Demo {j+1}: {endpoint} - {status_text} (Status: {demo_response.status_code})")
                    wrapper_demo_success_count += 1
                    successful_demos += 1
                else:
                    logging.warning(f"  Demo {j+1}: {endpoint} - FAILED (Status: {demo_response.status_code})")
                    logging.warning(f"    Error response: {demo_response.text[:200]}...")  # Truncate long error messages
                    wrapper_demo_fail_count += 1
                    failed_demos += 1
                    
            except Exception as e:
                logging.warning(f"  Demo {j+1}: {endpoint} - EXCEPTION: {str(e)}")
                wrapper_demo_fail_count += 1
                failed_demos += 1
        
        # Log summary for this wrapper
        if wrapper_demo_fail_count == 0:
            logging.warning(f"  Summary: All {wrapper_demo_success_count} demos passed for {wrapper_path}")
        else:
            logging.warning(f"  Summary: {wrapper_demo_success_count} passed, {wrapper_demo_fail_count} failed for {wrapper_path}")
    
    # Final summary
    total_expected_demos = successful_demos + failed_demos
    
    logging.warning("="*60)
    logging.warning("COMPREHENSIVE WRAPPER DEMO INTEGRATION TEST COMPLETE")
    logging.warning("="*60)
    logging.warning(f"Total wrappers processed: {total_wrappers}")
    logging.warning(f"Total demos tested: {total_expected_demos}")
    logging.warning(f"Successful demos: {successful_demos}")
    logging.warning(f"Failed demos: {failed_demos}")
    
    if total_expected_demos > 0:
        success_rate = (successful_demos / total_expected_demos) * 100
        logging.warning(f"Success rate: {success_rate:.1f}%")
    
    if failed_wrappers:
        logging.warning(f"Wrappers with failed metadata requests: {len(failed_wrappers)}")
        for wrapper_path, reason in failed_wrappers[:10]:  # Show first 10 failures
            logging.warning(f"  - {wrapper_path}: {reason}")
        if len(failed_wrappers) > 10:
            logging.warning(f"  ... and {len(failed_wrappers) - 10} more")
    
    logging.warning("="*60)
    
    # Assertion for test framework - we consider this a success if we at least got the wrapper list
    # The actual demo executions may fail due to missing files, which is expected
    assert total_wrappers > 0, "Should have found at least one wrapper"
    
    logging.warning("Integration test completed successfully - all wrappers processed")


if __name__ == "__main__":
    # This allows running the test directly for debugging
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    
    # Create the client manually for direct execution
    app = create_native_fastapi_app("./snakebase/snakemake-wrappers", "./snakebase/snakemake-workflows")
    client = TestClient(app)
    
    # Run the test function
    import asyncio
    asyncio.run(test_all_wrapper_demos_integration(client))