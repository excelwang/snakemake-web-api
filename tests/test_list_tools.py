import pytest

def test_list_tools_http(fastapi_client):
    """测试通过HTTP获取工具列表"""
    response = fastapi_client.get("/tools")
    assert response.status_code == 200
    
    data = response.json()
    assert "wrappers" in data
    assert "total_count" in data
    
    wrappers = data["wrappers"]
    assert len(wrappers) > 0, "Should have at least one wrapper"
    
    # Check for specific wrapper IDs that should be present (e.g., from snakemake-wrappers)
    # This requires that 'swa parse' has been run to populate the cache
    wrapper_ids = [wrapper["id"] for wrapper in wrappers]
    
    # Assuming 'bio/samtools/stats' is a common wrapper that should always be present
    assert "bio/samtools/stats" in wrapper_ids, "bio/samtools/stats wrapper not found in the list"
    
    # Optionally, check the structure of a single wrapper item
    first_wrapper = wrappers[0]
    assert "id" in first_wrapper
    assert "info" in first_wrapper
    assert "user_params" in first_wrapper
