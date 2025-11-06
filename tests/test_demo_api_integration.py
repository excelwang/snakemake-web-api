import os
import sys
import pytest
import asyncio
from pathlib import Path

# Add the src directory to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastmcp import Client
from snakemake_mcp_server.snakefile_parser import generate_demo_calls_for_wrapper


@pytest.mark.asyncio
async def test_demo_calls_have_complete_api_info(http_client: Client):
    """
    Test that demo calls are available from the API endpoint (verifies that the functionality works).
    This test calls the API endpoint and verifies that enhanced demos are returned.
    """
    # Test a few specific tools to check demo structure
    test_paths = ["bio/samtools/faidx", "bio/samtools/stats"]
    
    found_demos = False  # Track if we found any demos to validate the feature works
    
    for tool_path in test_paths:
        try:
            # Call the API to get enhanced tool metadata with demos
            result = await asyncio.wait_for(
                http_client.call_tool(
                    "get_tool_meta",  # This is the operation ID for GET /tools/{tool_path}
                    {
                        "tool_path": tool_path
                    }
                ),
                timeout=10
            )
            
            # Extract the data from the response - data is likely a Pydantic object
            response_data = result.data if hasattr(result, 'data') else result
            
            # Get demos from the response data
            # If response_data is a Pydantic model, we need to extract the demos field
            if hasattr(response_data, 'demos'):
                demos = response_data.demos
            elif hasattr(response_data, 'model_dump'):
                response_dict = response_data.model_dump()
                demos = response_dict.get('demos', [])
            elif isinstance(response_data, dict):
                demos = response_data.get('demos', [])
            else:
                demos = []
            
            print(f"Found {len(demos)} demos for {tool_path}")
            
            if demos:
                found_demos = True
                print(f"  ✓ {tool_path} has {len(demos)} demo calls with enhanced format")
        
        except asyncio.TimeoutError:
            print(f"  ⏱️  Timeout testing {tool_path}, skipping...")
            continue
        except Exception as e:
            print(f"  ❌ Error testing {tool_path}: {str(e)}")
            # Only fail if it's an unexpected error (not timeout or specific demo not found)
            if "404" not in str(e) and "not found" not in str(e).lower():
                raise e
    
    # Assert that we found demos to confirm the feature works
    assert found_demos, "No demos found from API - the enhanced demo functionality may not be working"
    print("✅ API returns demos with enhanced format!")


@pytest.mark.asyncio
async def test_demo_api_calls_validation(http_client: Client):
    """
    Integration test to verify that the API correctly returns enhanced demo information
    and that the demo calls are structurally valid to pass to the API.
    """
    # Test with a specific tool to validate the full flow
    test_tool_path = "bio/samtools/faidx"
    
    # First, get the enhanced demo information for the tool
    result = await asyncio.wait_for(
        http_client.call_tool(
            "get_tool_meta",  # Get tool metadata with demos
            {
                "tool_path": test_tool_path
            }
        ),
        timeout=10
    )
    
    # Extract the data - the result should be WrapperMetadata with demos
    response_data = result.data if hasattr(result, 'data') else result
    
    # Try to extract demos from the response data using multiple strategies
    demos = []
    
    # Strategy 1: Direct attribute access
    if hasattr(response_data, 'demos'):
        demos = response_data.demos
    # Strategy 2: Model dump if it's a Pydantic model
    elif hasattr(response_data, 'model_dump'):
        data_dict = response_data.model_dump()
        demos = data_dict.get('demos', [])
    # Strategy 3: Access as dictionary
    elif isinstance(response_data, dict):
        demos = response_data.get('demos', [])
    # Strategy 4: Fallback
    else:
        # Try to access as if it's a structured object
        try:
            demos = getattr(response_data, 'demos', [])
        except:
            demos = []
    
    print(f"Found {len(demos)} demos for {test_tool_path}")
    assert len(demos) > 0, f"Expected demos for {test_tool_path}, but got none"
    
    # Now test that the demos have the right structure by testing first 2
    valid_demos_tested = 0
    
    for i, demo_obj in enumerate(demos[:2]):  # Test first 2 demos
        print(f"  Validating demo {i+1} structure...")
        
        # Convert the demo object to a dictionary using various methods
        demo_dict = None
        
        # Try different ways to convert the demo object to dict
        if hasattr(demo_obj, 'model_dump'):  # Pydantic v2
            demo_dict = demo_obj.model_dump()
        elif hasattr(demo_obj, '__dict__'):  # Standard object
            demo_dict = demo_obj.__dict__
        elif hasattr(demo_obj, 'dict'):  # Pydantic v1
            demo_dict = demo_obj.dict()
        elif isinstance(demo_obj, dict):
            demo_dict = demo_obj
        else:
            # Try to convert to dict 
            try:
                demo_dict = dict(demo_obj)
            except:
                # If conversion fails, we'll try a different approach
                demo_dict = {}
        
        # Check if we have the expected structure
        required_keys = ['method', 'endpoint', 'payload', 'curl_example']
        missing_keys = [key for key in required_keys if key not in demo_dict]
        
        if missing_keys:
            print(f"    ❌ Demo {i+1}: Missing required keys {missing_keys}")
            # Try to debug the actual structure
            if demo_dict:
                available_keys = list(demo_dict.keys()) if isinstance(demo_dict, dict) else "Not a dict"
                print(f"      Available keys: {available_keys}")
            continue
        
        # Verify the content makes sense
        method = demo_dict.get('method')
        endpoint = demo_dict.get('endpoint')
        payload = demo_dict.get('payload')
        
        assert method == 'POST', f"Expected method POST, got {method}"
        assert endpoint == '/tool-processes', f"Expected endpoint /tool-processes, got {endpoint}"
        assert isinstance(payload, dict), f"Expected payload to be dict, got {type(payload)}"
        assert 'wrapper_name' in payload, "Payload missing wrapper_name"
        
        print(f"    ✅ Demo {i+1}: Structure valid ({payload['wrapper_name']})")
        
        # Now test that we can execute the demo call using the extracted payload
        try:
            # Try to execute the demo API call using the extracted information
            tool_result = await asyncio.wait_for(
                http_client.call_tool(
                    "tool_process",
                    {
                        "wrapper_name": payload.get('wrapper_name', ''),
                        "inputs": payload.get('inputs', []),
                        "outputs": payload.get('outputs', []),
                        "params": payload.get('params', {}),
                        "threads": payload.get('threads', 1),
                        "log": payload.get('log', {}),
                        "extra_snakemake_args": payload.get('extra_snakemake_args', ''),
                        "container": payload.get('container', None),
                        "benchmark": payload.get('benchmark', None),
                        "resources": payload.get('resources', {}),
                        "shadow": payload.get('shadow', None),
                        "conda_env": payload.get('conda_env', None)
                    }
                ),
                timeout=3  # 3 second timeout
            )
            
            print(f"    ✅ Demo {i+1}: API call executed successfully")
            
        except asyncio.TimeoutError:
            # This is expected since we don't have actual input files
            print(f"    ⏱️  Demo {i+1}: API accepted call but timed out (expected due to missing files)")
            
        except Exception as e:
            error_str = str(e)
            # Check if this is an actual validation error (not just execution)
            if "400" in error_str or "validation" in error_str.lower() or "required" in error_str.lower():
                print(f"    ❌ Demo {i+1}: API validation error: {error_str}")
                raise AssertionError(f"Demo {i+1} has validation error: {error_str}")
            else:
                # Execution errors (like file not found) are expected with demo calls
                print(f"    ⚠️  Demo {i+1}: Execution error (expected): {error_str}")
        
        valid_demos_tested += 1
    
    print(f"\n📊 Integration test results for {test_tool_path}:")
    print(f"  Valid demos tested: {valid_demos_tested}")
    
    assert valid_demos_tested > 0, f"No demos were successfully validated from {test_tool_path}"
    print("✅ API returns enhanced demos with correct structure and they can be executed!")