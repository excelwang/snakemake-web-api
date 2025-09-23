import pytest
import asyncio
from fastmcp import Client

@pytest.mark.asyncio
async def test_list_tools_http(http_client: Client):
    """测试通过HTTP获取工具列表"""
    tools = await asyncio.wait_for(http_client.list_tools(), timeout=15)
    
    assert len(tools) > 0, "Should have at least one tool"
    
    tool_names = [tool.name for tool in tools]
    assert "run_snakemake_wrapper" in tool_names, \
        f"run_snakemake_wrapper not found in {tool_names}"
