# Snakemake MCP Server

The Snakemake MCP (Micro-service Communication Protocol) Server provides a robust API endpoint for remotely executing Snakemake wrappers and full Snakemake workflows. This allows for flexible integration of Snakemake-based bioinformatics pipelines into larger systems or applications.

## Key Features

*   **`run_snakemake_wrapper` Tool:** Execute individual Snakemake wrappers by name. This is ideal for running specific bioinformatics tools wrapped for Snakemake.
*   **`run_snakemake_workflow` Tool:** Execute entire Snakemake workflows. This enables running complex, multi-step pipelines remotely.
*   **Flexible Parameter Passing:** Both tools accept common Snakemake parameters such as `inputs`, `outputs`, `params`, `threads`, `log`, `extra_snakemake_args`, `container`, `benchmark`, `resources`, `shadow`, `conda_env`, and `target_rule` (for workflows).
*   **Dynamic Config Modification (for Workflows):** The `run_snakemake_workflow` tool can dynamically modify a workflow's `config.yaml` based on parameters provided in the API call, allowing for on-the-fly customization of workflow execution.
*   **Conda Environment Management:** Seamless integration with Conda environments via the `conda_env` parameter, ensuring reproducible and isolated execution environments.

## Installation and Setup

To run the Snakemake MCP Server, you need to have Snakemake and Conda (or Mamba) installed in your environment.

1.  **Clone the `snakemake-wrappers` repository:**
    ```bash
    git clone https://github.com/snakemake/snakemake-wrappers.git
    ```
    This repository contains the wrappers that the server will execute.

2.  **Clone or prepare your Snakemake workflows:**
    Ensure your Snakemake workflows (e.g., `rna-seq-star-deseq2`) are accessible on the server's filesystem. For example, you might have them in a `snakebase` directory alongside `snakemake-wrappers`.

3.  **Run the Server:**
    Navigate to the `snakemake-mcp-server` directory and start the server using the `click` CLI:

    ```bash
    cd snakemake-mcp-server
    python -m src.snakemake_mcp_server.server run \
        --host 127.0.0.1 \
        --port 8081 \
        --wrappers-path /path/to/your/snakemake-wrappers \
        --workflow-base-dir /path/to/your/snakebase
    ```
    *   Replace `/path/to/your/snakemake-wrappers` with the absolute path to your cloned `snakemake-wrappers` repository.
    *   Replace `/path/to/your/snakebase` with the absolute path to the base directory containing your Snakemake workflows (e.g., the parent directory of `rna-seq-star-deseq2`).

## Usage Examples

### Executing a Single Snakemake Wrapper (`run_snakemake_wrapper`)

This example demonstrates how to run the `samtools/faidx` wrapper.

```python
import asyncio
from fastmcp import Client

async def main():
    client = Client("http://127.0.0.1:8081/mcp")
    async with client:
        try:
            result = await client.call_tool(
                "run_snakemake_wrapper",
                {
                    "wrapper_name": "samtools/faidx",
                    "inputs": ["/tmp/test_genome.fasta"],
                    "outputs": ["/tmp/test_genome.fasta.fai"],
                    "params": {},
                    "threads": 1,
                    # Optional: Specify a conda environment for the wrapper
                    "conda_env": "/path/to/your/conda_env.yaml",
                    # Optional: Run with shadow mode
                    "shadow": "minimal",
                }
            )
            print(f"Wrapper execution successful: {result.data}")
        except Exception as e:
            print(f"Wrapper execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Executing a Full Snakemake Workflow (`run_snakemake_workflow`)

This example shows how to run a workflow like `rna-seq-star-deseq2` and dynamically override a parameter in its `config.yaml`.

Assume your `rna-seq-star-deseq2` workflow has a `config/config.yaml` like this:

```yaml
message: "default message"
```

And its `workflow/Snakefile` uses `config["message"]`.

```python
import asyncio
from fastmcp import Client

async def main():
    client = Client("http://127.0.0.1:8081/mcp")
    async with client:
        try:
            result = await client.call_tool(
                "run_snakemake_workflow",
                {
                    "workflow_name": "rna-seq-star-deseq2",
                    "outputs": ["/path/to/workflow/output.txt"], # Example output
                    "params": {"message": "hello from mcp server"}, # Override config parameter
                    "threads": 8,
                    # Optional: Target a specific rule within the workflow
                    "target_rule": "all",
                    "conda_env": "/path/to/your/workflow_conda_env.yaml",
                }
            )
            print(f"Workflow execution successful: {result.data}")
        except Exception as e:
            print(f"Workflow execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```