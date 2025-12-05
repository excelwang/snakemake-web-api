import pytest
import os


def test_get_tool_meta_api(fastapi_client):
    """测试获取特定tool metadata的API"""
    # 调用新添加的get_tool_meta工具，使用存在的tool路径
    response = fastapi_client.get("/tools/bio/samtools/stats")
    assert response.status_code == 200
    
    # 检查返回数据结构 - data is a Pydantic model
    data = response.json()
    assert "id" in data, "Response should have id"
    assert "info" in data, "Response should have info"
    assert "user_params" in data, "Response should have user_params"
    
    # 验证返回的tool信息
    assert data["id"] == "bio/samtools/stats", f"Path should be 'bio/samtools/stats', got {data['id']}"
    assert isinstance(data["info"]["name"], str), "Tool name should be string"
    
    print(f"Tool id: {data['id']}")
    print(f"Tool name: {data['info']['name']}")
    print(f"Tool description: {data['info']['description']}")
    
    # 这个tool應該有基本的input/output/params信息
    print(f"Tool input: {data['user_params']['inputs']}")
    print(f"Tool output: {data['user_params']['outputs']}")


def test_get_tool_meta_not_found(fastapi_client):
    """测试获取不存在的tool metadata的错误处理"""
    response = fastapi_client.get("/tools/nonexistent/tool")
    assert response.status_code == 404
    assert "Tool metadata cache not found for" in response.json()["detail"]