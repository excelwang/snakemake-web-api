"""
Integration tests for FastMCP-wrapped Snakemake functionality.

These tests verify the MCP interface that wraps the FastAPI application.
"""
import pytest
import asyncio
from fastmcp import FastMCP
from snakemake_mcp_server.api.main import create_native_fastapi_app


# Placeholder tests to validate the test file structure
# The actual MCP transport setup might be complex and requires specific infrastructure
# For the purpose of test file splitting, we validate the concepts


def test_mcp_server_creation():
    """Test that MCP server can be created from FastAPI app."""
    # Create the native FastAPI app first
    fastapi_app = create_native_fastapi_app("./snakebase", "./snakebase/workflows")
    
    # Create MCP server from FastAPI app using FastMCP.from_fastapi()
    mcp_server = FastMCP.from_fastapi(fastapi_app, name="Test Snakemake API")
    
    # Just verify the server object was created
    assert mcp_server is not None
    print("MCP server created successfully from FastAPI app")


@pytest.mark.asyncio
async def test_mcp_wrapper_execution():
    """Placeholder: Test MCP wrapper execution (would require transport)."""
    # This is a conceptual test - actual implementation requires transport setup
    pytest.skip("MCP transport setup requires infrastructure, conceptual test only")


@pytest.mark.asyncio
async def test_mcp_demo_structure_validation():
    """Placeholder: Test MCP demo structure validation (would require transport)."""
    # This is a conceptual test - actual implementation requires transport setup
    pytest.skip("MCP transport setup requires infrastructure, conceptual test only")