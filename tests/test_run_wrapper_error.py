import pytest
import asyncio
from fastmcp import Client

@pytest.mark.asyncio
async def test_run_wrapper_http_error_handling(http_client: Client, test_files):
    """测试HTTP错误处理"""
    with pytest.raises(Exception) as exc_info:
        await asyncio.wait_for(
            http_client.call_tool(
                "run_snakemake_wrapper",
                {
                    "wrapper_name": "",  # 无效参数
                    "inputs": [test_files['input']],
                    "outputs": [test_files['output']],
                    "params": {},
                    "threads": 1
                }
            ),
            timeout=30
        )
    
    assert "'wrapper_name' must be provided for wrapper execution." in str(exc_info.value)