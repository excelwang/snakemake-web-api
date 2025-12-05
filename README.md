# Snakemake Web API

The Snakemake Web API provides robust endpoints for remotely executing Snakemake wrappers and full Snakemake workflows. This allows for flexible integration of Snakemake-based bioinformatics pipelines into larger systems or applications. The API is available as a traditional REST API.

## Key Features

*   **REST API Support:** REST API endpoints are available for maximum flexibility.
*   **`run_snakemake_wrapper` Tool:** Execute individual Snakemake wrappers by name. This is ideal for running specific bioinformatics tools wrapped for Snakemake.
*   **`run_snakemake_workflow` Tool:** Execute entire Snakemake workflows. This enables running complex, multi-step pipelines remotely.
*   **Flexible Parameter Passing:** Both tools accept common Snakemake parameters such as `inputs`, `outputs`, `params`, `threads`, `log`, `extra_snakemake_args`, `container`, `benchmark`, `resources`, `shadow`, and `target_rule`.
*   **Dynamic Config Modification (for Workflows):** The `run_snakemake_workflow` tool can dynamically modify a workflow's `config.yaml` based on parameters provided in the API call, allowing for on-the-fly customization of workflow execution.
*   **Async Job Processing:** Asynchronous job submission and status checking with support for long-running tasks.
*   **Conda Environment Management:** Seamless integration with Conda environments, ensuring reproducible and isolated execution environments.

## Installation

### Prerequisites

* Install `uv` package manager from [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv)
* Install `conda` (either [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Mambaforge](https://github.com/conda-forge/miniforge#mambaforge))
* Ensure you have Python 3.12+ installed

### Installation Steps

1. **Clone the repository:**
    ```bash
    git clone https://github.com/excelwang/snakemake-web-api.git
    cd snakemake-web-api
    ```

2. **Install project dependencies:**
    ```bash
    uv sync
    ```

3. **Activate the virtual environment:**
    ```bash
    source .venv/bin/activate  # On Linux/macOS
    # or
    .venv\Scripts\activate     # On Windows
    ```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SNAKEBASE_DIR` | Base directory for `snakemake-wrappers` and `snakemake-workflows` subdirectories | `~/snakebase` |
| `SNAKEMAKE_CONDA_PREFIX` | Path to conda environments for Snakemake | `~/.snakemake/conda` |

### Setting up the `snakebase` Directory

The `snakemake-web-api` relies on a specific directory structure to locate Snakemake wrappers and workflows. This base directory is referred to as `snakebase`. By default, the server looks for a directory named `snakebase` in the current working directory. The location of this directory can be customized by setting the `SNAKEBASE_DIR` environment variable.

The `snakebase` directory must contain the following subdirectories:

*   `snakemake-wrappers`: This directory should be a clone of the official Snakemake wrappers repository.
*   `snakemake-workflows`: This directory should contain the Snakemake workflows that you want to expose through the server.

1.  **Create the `snakebase` directory:**
    ```bash
    mkdir snakebase
    cd snakebase
    ```

2.  **Clone the `snakemake-wrappers` repository:**
    ```bash
    git clone https://github.com/snakemake/snakemake-wrappers.git
    ```

3.  **Add your Snakemake workflows:**
    Create a directory named `snakemake-workflows` and place your workflow directories inside it. For example:
    ```bash
    mkdir snakemake-workflows
    cd snakemake-workflows
    git clone https://github.com/snakemake-workflows/rna-seq-star-deseq2
    git clone https://github.com/snakemake-workflows/dna-seq-varlociraptor
    git clone https://github.com/excelwang/StainedGlass
    # etc.
    ```

## Quick Test Walkthrough

This section guides you through a quick test of the system to verify everything is working correctly.

### 1. Parse Wrappers

First, parse and cache all wrapper metadata:

```bash
export SNAKEBASE_DIR=~/snakebase # optional
swa parse
```

This will scan your `snakemake-wrappers` directory and cache metadata for faster server startup.

### 2. Start REST API Server

Start the REST API server to access web endpoints:

```bash
swa rest --host 127.0.0.1 --port 8082
```

### 3. Verify Server Status

Check that your server is running:

```bash
curl http://127.0.0.1:8082/health
```

You should get a response indicating the server is healthy.

### 4. List Available Tools

Get a list of available Snakemake wrappers:

```bash
curl http://127.0.0.1:8082/tools
```

### 5. Run a Demo Wrapper

To run a demo wrapper automatically, use the provided script that executes the demo case from the API:

```bash
# Make sure the script is executable
chmod +x run_demo_wrapper.sh

# Run the demo wrapper
./run_demo_wrapper.sh
```

This script will:
1. Fetch a demo case from the `/demo-case` endpoint
2. Execute the wrapper via the `/tool-processes` REST API endpoint
3. Poll the job status until completion
4. Verify the final job status

## Running the Server

The server offers different modes based on your needs:

### REST API Server
To start the REST API server:

```bash
swa rest --host 127.0.0.1 --port 8082
```

### Parsing Wrappers
To parse and cache metadata for all available Snakemake wrappers:

```bash
swa parse
```

### Verifying Installation
To verify that your installation is working correctly:

```bash
swa verify
```

For a complete list of options, see the [CLI Commands Guide](CLI_COMMANDS.md).