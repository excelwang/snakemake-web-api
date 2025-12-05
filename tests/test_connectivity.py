import pytest

def test_server_connectivity(fastapi_client):
    """测试服务器连通性"""
    response = fastapi_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "snakemake-native-api"}