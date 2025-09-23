import pytest
import asyncio
import os
from fastmcp import Client

@pytest.mark.asyncio
async def test_run_wrapper_with_shadow(http_client: Client, test_files):
    """测试通过HTTP成功执行带有shadow指令的wrapper"""
    # 1. 调用 run_snakemake_wrapper，并设置 shadow 参数
    result = await asyncio.wait_for(
        http_client.call_tool(
            "run_snakemake_wrapper",
            {
                "wrapper_name": "samtools/faidx",
                "inputs": [test_files['input']],
                "outputs": [test_files['output']],
                "params": {},
                "threads": 1,
                "shadow": "minimal", # 设置 shadow 指令为 "minimal"
            }
        ),
        timeout=120  # Snakemake 执行可能需要更多时间
    )
    
    # 2. 验证结果
    assert hasattr(result, 'data'), "Result should have data attribute"
    assert isinstance(result.data, dict), "Result data should be a dictionary"
    
    assert result.data.get('status') == 'success', \
        f"Expected success, got {result.data.get('status')}: {result.data.get('error_message')}"
    
    # 3. 验证输出文件是否存在于最终位置
    assert os.path.exists(test_files['output']), \
        f"Output file should be created: {test_files['output']}"
    
    # 4. 验证文件内容 (与 test_run_wrapper_http_success 相同)
    with open(test_files['output'], 'r') as f:
        content = f.read().strip()
        assert len(content) > 0, "Output file should not be empty"
        assert '\t' in content, "FAI file should be tab-delimited"


