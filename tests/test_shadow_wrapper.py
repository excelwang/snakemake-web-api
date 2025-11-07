import pytest
import os
from snakemake_mcp_server.wrapper_runner import run_wrapper

def test_run_wrapper_with_shadow(test_files):
    """测试通过直接函数调用成功执行带有shadow指令的wrapper"""
    # Get the wrappers path
    wrappers_path = os.environ.get("SNAKEBASE_DIR", "./snakebase") + "/snakemake-wrappers"
    if not os.path.exists(wrappers_path):
        wrappers_path = "./snakebase/snakemake-wrappers"
    
    # 1. 调用 run_wrapper，并设置 shadow 参数
    result = run_wrapper(
        wrapper_name="bio/samtools/faidx",
        wrappers_path=wrappers_path,
        inputs=[test_files['input']],
        outputs=[test_files['output']],
        params={},
        threads=1,
        shadow="minimal", # 设置 shadow 指令为 "minimal"
    )
    
    # 2. 验证结果
    assert 'status' in result, "Result should have status attribute"
    
    assert result['status'] == 'success', \
        f"Expected success, got {result.get('status')}: {result.get('error_message')}"
    
    # 3. 驗證輸出文件是否存在於最終位置
    assert os.path.exists(test_files['output']), \
        f"Output file should be created: {test_files['output']}"
    
    # 4. 驗證文件內容 (與 test_run_wrapper_success 相同)
    with open(test_files['output'], 'r') as f:
        content = f.read().strip()
        assert len(content) > 0, "Output file should not be empty"
        assert '\t' in content, "FAI file should be tab-delimited"


