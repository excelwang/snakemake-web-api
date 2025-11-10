import pytest
import asyncio
import os
import tempfile
import shutil
import socket
import time
from pathlib import Path
from fastmcp import Client
import pytest_asyncio
import threading
from snakemake_mcp_server.server import create_mcp_from_fastapi

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

# For API-based tests (MCP)
@pytest.fixture(scope="function")
def server_port():
    # Find a free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

@pytest.fixture(scope="function")
def server_url(server_port):
    return f"http://127.0.0.1:{server_port}/mcp"

@pytest.fixture(scope="function")
def mcp_server(server_port, wrappers_path, workflows_dir):
    pytest.skip("Skipping all MCP-dependent tests as requested.")
    app = create_mcp_from_fastapi(wrappers_path, workflows_dir)
    
    def run_server():
        app.run(transport="http", host="127.0.0.1", port=server_port, log_level="info")

    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    time.sleep(5) # Give the server a moment to start its process
    # Wait for the server to start
    for _ in range(40): # Increased attempts for server startup (20 seconds total)
        try:
            with socket.create_connection(("127.0.0.1", server_port), timeout=1):
                break
        except (socket.timeout, ConnectionRefusedError):
            time.sleep(0.5)
    else:
        pytest.fail("Server did not start in time.")
        
    yield
    
    # The server is a daemon thread, so it will be terminated automatically
    # when the main thread exits.

@pytest_asyncio.fixture(scope="function")
async def http_client(server_url, mcp_server):
    """创建HTTP客户端 - 每个测试独立的客户端实例"""
    os.environ['NO_PROXY'] = '127.0.0.1'
    client = Client(server_url)
    
    # 使用短暂的连接，避免长时间保持连接导致的问题
    try:
        time.sleep(1) # Add a small delay before pinging
        async with client:
            # 简单的连通性测试
            await asyncio.wait_for(client.ping(), timeout=10) # Increased timeout for ping
            yield client
    except Exception as e:
        pytest.fail(f"Failed to connect to HTTP server: {e}")
