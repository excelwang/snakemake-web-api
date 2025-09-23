import pytest
from fastmcp import Client

@pytest.mark.asyncio
async def test_server_connectivity(http_client: Client):
    """测试服务器连通性"""
    assert http_client.is_connected()