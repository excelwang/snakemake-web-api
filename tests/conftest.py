import pytest
import asyncio
import os
import tempfile
import shutil
from pathlib import Path
import pytest_asyncio
from snakemake_mcp_server.schemas import InternalWrapperRequest

@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()

SNAKEBASE_DIR = os.environ.get("SNAKEBASE_DIR")

@pytest.fixture(scope="session")
def snakebase_dir():
    if not SNAKEBASE_DIR:
        pytest.fail("SNAKEBASE_DIR environment variable not set.")
    return os.path.abspath(SNAKEBASE_DIR)

@pytest.fixture(scope="session")
def wrappers_path(snakebase_dir):
    return os.path.join(snakebase_dir, "snakemake-wrappers")

@pytest.fixture(scope="session")
def workflows_dir(snakebase_dir):
    return os.path.join(snakebase_dir, "snakemake-workflows")

@pytest_asyncio.fixture(scope="function")
async def run_wrapper_test():
    """创建一个封装了run_wrapper调用的fixture，接口与/tool-processes相同"""
    from snakemake_mcp_server.wrapper_runner import run_wrapper
    
    with tempfile.TemporaryDirectory() as workdir:
        async def wrapper_runner_async(wrapper_id, inputs=None, outputs=None, params=None):
            request = InternalWrapperRequest(
                wrapper_id=wrapper_id,
                inputs=inputs,
                outputs=outputs,
                params=params,
                workdir=workdir,
                threads=1
            )
            return await run_wrapper(request=request)
        
        # 返回包装器运行器异步函数和工作目录
        yield wrapper_runner_async, workdir

@pytest.fixture(scope="function")
def test_files():
    """创建测试文件"""
    temp_dir = tempfile.mkdtemp(prefix="direct_func_test_")
    test_input = Path(temp_dir) / "test_genome.fasta"
    test_output = Path(temp_dir) / "test_genome.fasta.fai"
    
    # 创建测试FASTA文件
    with open(test_input, 'w') as f:
        f.write(">chr1\nATCGATCGATCGATCGATCG\n")
        f.write(">chr2\nGCTAGCTAGCTAGCTAGCTA\n")
    
    yield {
        'input': str(test_input),
        'output': str(test_output),
        'temp_dir': temp_dir
    }
    
    # 清理
    try:
        shutil.rmtree(temp_dir)
    except Exception as e:
        print(f"Warning: Failed to clean up {temp_dir}: {e}")