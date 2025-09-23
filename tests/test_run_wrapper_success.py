import pytest
import asyncio
import os
from fastmcp import Client

@pytest.mark.asyncio
async def test_run_wrapper_http_success(http_client: Client, test_files):
    """测试通过HTTP成功执行wrapper"""
    result = await asyncio.wait_for(
        http_client.call_tool(
            "run_snakemake_wrapper",
            {
                "wrapper_name": "samtools/faidx",
                "inputs": [test_files['input']],
                "outputs": [test_files['output']],
                "params": {},
                "threads": 1
            }
        ),
        timeout=120  # Snakemake 执行需要更多时间
    )
    
    # 验证结果
    assert hasattr(result, 'data'), "Result should have data attribute"
    assert isinstance(result.data, dict), "Result data should be a dictionary"
    
    # 验证执行状态
    assert result.data.get('status') == 'success', \
        f"Expected success, got {result.data.get('status')}: {result.data.get('error_message')}"
    
    # 验证输出文件
    assert os.path.exists(test_files['output']), \
        f"Output file should be created: {test_files['output']}"
    
    # 验证文件内容
    with open(test_files['output'], 'r') as f:
        content = f.read().strip()
        assert len(content) > 0, "Output file should not be empty"
        assert '\t' in content, "FAI file should be tab-delimited"
