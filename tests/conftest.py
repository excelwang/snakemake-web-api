import pytest
import asyncio
import os
import tempfile
import shutil
import socket
import time
from pathlib import Path
import pytest_asyncio
import threading
from fastapi.testclient import TestClient
from snakemake_mcp_server.api.main import create_native_fastapi_app

SNAKEBASE_DIR = os.environ.get("SNAKEBASE_DIR")

@pytest.fixture(scope="session")
def snakebase_dir():
    # If SNAKEBASE_DIR is not set, use a default path within the project
    _snakebase_path = SNAKEBASE_DIR if SNAKEBASE_DIR else "/root/snakemake-mcp-server/snakebase"
    
    if not Path(_snakebase_path).exists():
        pytest.fail(f"SNAKEBASE_DIR '{_snakebase_path}' does not exist. Please set the SNAKEBASE_DIR environment variable or create the directory.")
    
    return os.path.abspath(_snakebase_path)

@pytest.fixture(scope="session")
def wrappers_path(snakebase_dir):
    return os.path.join(snakebase_dir, "snakemake-wrappers")

@pytest.fixture(scope="session")
def workflows_dir(snakebase_dir):
    return os.path.join(snakebase_dir, "snakemake-workflows")

from snakemake_mcp_server.schemas import InternalWrapperRequest, UserProvidedParams

@pytest_asyncio.fixture(scope="function")
async def run_wrapper_test(): # Removed wrappers_path here
    """创建一个封装了run_wrapper调用的fixture，接口与/tool-processes相同"""
    from snakemake_mcp_server.wrapper_runner import run_wrapper
    
    with tempfile.TemporaryDirectory() as temp_workdir_str:
        temp_workdir = Path(temp_workdir_str)
        
        async def wrapper_runner_async(wrapper_id: str, inputs=None, outputs=None, params=None, platform_params=None):
            # Ensure workdir exists, even if it's empty
            temp_workdir.mkdir(parents=True, exist_ok=True)

            user_req_params = UserProvidedParams(
                inputs=inputs,
                outputs=outputs,
                params=params
            )
            
            internal_request = InternalWrapperRequest(
                wrapper_id=wrapper_id,
                workdir=str(temp_workdir),
                **user_req_params.model_dump(exclude_none=True),
                **(platform_params.model_dump(exclude_none=True) if platform_params else {})
            )
            return await run_wrapper(request=internal_request) # Removed wrappers_path here
        yield wrapper_runner_async, temp_workdir_str


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

@pytest.fixture(scope="function")
def fastapi_client(wrappers_path, workflows_dir):
    """
    Fixture that provides a TestClient for the FastAPI application.
    This client can be used to make synchronous requests to the FastAPI app.
    """
    app = create_native_fastapi_app(wrappers_path, workflows_dir)
    with TestClient(app) as client:
        yield client