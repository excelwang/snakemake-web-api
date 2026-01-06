# Snakemake Web API

The Snakemake Web API provides robust endpoints for remotely executing Snakemake wrappers and full Snakemake workflows. This allows for flexible integration of Snakemake-based bioinformatics pipelines into larger systems or applications.

## Key Features

*   **FastAPI REST API:** High-performance REST endpoints for discovering and executing Snakemake wrappers and workflows, with automatic OpenAPI documentation.
*   **Asynchronous Job Processing:** Submit long-running tasks and monitor their progress via a standardized job status API.
*   **Metadata Caching:** Pre-parse Snakemake wrappers and workflows to provide fast access to tool information and executable demos.
*   **Dynamic Configuration:** Support for on-the-fly modification of workflow `config.yaml` and wrapper parameters.
*   **Flexible Environment Management:** Seamlessly handles Conda and Container (Singularity) environments.

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
    git clone https://github.com/excelwang/rna-seq-star-deseq2
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

## API Endpoints Summary

*   `GET /tools`: List all available Snakemake wrappers.
*   `GET /workflows`: List all available workflows.
*   `POST /tool-processes`: Submit an asynchronous wrapper execution job.
*   `POST /workflow-processes`: Submit an asynchronous workflow execution job.
*   `GET /tool-processes/{job_id}`: Check the status of a specific job.
*   `GET /demos/wrappers/{wrapper_id}`: Get executable demo payloads for a specific wrapper.
*   `GET /demos/workflows/{workflow_id}`: Get executable demo payloads for a specific workflow.

## Discovering and Using Demos

The API automatically generates "Demos" by analyzing the test cases provided in the Snakemake wrapper repository and the `demos/` directory of workflows.

### 1. Get Wrapper Demos
Discover how to call a specific wrapper with valid test data:
```bash
curl http://localhost:8082/demos/wrappers/bio/fastp
```
This returns a list of objects containing the `method`, `endpoint`, and a pre-populated `payload` that you can send directly to `/tool-processes`.

### 2. Get Workflow Demos
See example configurations for a specific workflow:
```bash
curl http://localhost:8082/demos/workflows/rna-seq-star-deseq2
```
This returns various configuration presets (e.g., "small-test-dataset", "human-genome-config") that can be used in the `config` field of a `/workflow-processes` submission.

## Working with Workflows

The Workflow API allows you to manage and execute complex Snakemake pipelines.

### 1. List Available Workflows
Retrieve a list of all workflows found in your `snakemake-workflows` directory:
```bash
curl http://localhost:8082/workflows
```

### 2. Get Workflow Metadata
Get detailed information about a specific workflow, including its default configuration and parameter schema:
```bash
curl http://localhost:8082/workflows/my-cool-pipeline
```

### 3. Submit a Workflow Job
Execute a workflow by providing its ID and optional configuration overrides. The server performs a **deep merge** of your `config` object into the workflow's base `config.yaml`.

```bash
curl -X POST http://localhost:8082/workflow-processes \
     -H "Content-Type: application/json" \
     -d '{
           "workflow_id": "rna-seq-star-deseq2",
           "config": {
             "samples": "samples.tsv",
             "params": {
               "star": { "index": "", "align": "" }
             }
           },
           "target_rule": "all"
         }'
```

### 4. Kubernetes & S3 Execution (Best Practices)

When running workflows in a distributed K8s + S3 environment, keep the following in mind:

*   **Data Pre-provisioning**: If your server is started with the `--prefill` flag and a K8s profile, SWA will automatically sync your local isolated workdir (including symlinked input data) to S3 before execution.
*   **Workflow Localization**: Always use **complete, localized workflow code**. Avoid using remote `include` directives (e.g., URLs pointing to GitHub) in your Snakefiles. Snakemake's Kubernetes executor may fail with a `TypeError` when attempting to archive remote source files for Pod distribution. Ensure all `.smk` rules are present within the workflow directory.
*   **Dynamic Prefixing**: SWA automatically generates unique S3 prefixes based on the `job_id` to prevent data collisions between concurrent runs.

### 5. Configuring Snakemake Profiles

Profiles allow you to define execution strategies (like Kubernetes, SLURM, or local) and storage settings in a reusable way.

#### Profile Search Priority
SWA looks for the profile specified by `--workflow-profile` in the following order:
1.  **Workflow-specific**: `{workflow_dir}/workflow/profiles/{profile_name}/`
2.  **Global SWA**: `~/.swa/profiles/{profile_name}/` (Recommended for sharing K8s config across workflows)
3.  **System Default**: Snakemake's standard paths (e.g., `~/.config/snakemake/`)

#### Demo Profile: `k3s-s3`
To run workflows on Kubernetes with S3 storage, create a directory `~/.swa/profiles/k3s-s3/` and add a `config.yaml` file.

**Note on Stability**: We highly recommend a custom image with pre-installed storage plugins to avoid slow runtime `pip install` steps that can cause timeouts.

```yaml
# ~/.swa/profiles/k3s-s3/config.yaml

# 1. 使用 K3s (Kubernetes) 执行器
executor: kubernetes
jobs: 10

# 2. 设置默认的 S3 存储提供商
default-storage-provider: s3
default-storage-prefix: s3://whj/

# 3. 将 S3/MinIO 凭证和服务器地址注入到 K3s Pods 中
envvars:
  - AWS_ACCESS_KEY_ID
  - AWS_SECRET_ACCESS_KEY
  - AWS_ENDPOINT_URL

# 4. 使用 Conda 环境
use-conda: true
conda-frontend: mamba

# 5. 其他配置
latency-wait: 120
rerun-incomplete: true
rerun-triggers: mtime
show-failed-logs: false
printshellcmds: true
keep-going: false

# 6. Kubernetes Pod 配置
container-image: snakemake/snakemake:v9.11.2
storage-s3-endpoint-url: http://10.3.217.200:20480
storage-s3-max-requests-per-second: 100
kubernetes-namespace: default
# 保持 pod 以便调试 (生产环境可设为 false)
kubernetes-omit-job-cleanup: true

# 7. 全局稳定性设置
# 增加重试次数以应对集群 API 波动
retries: 10

# 8. 使用自定义 Kubernetes Job 模板以设置 backoffLimit
# 这能极大地提高在高负载 K8s 环境下的运行成功率
kubernetes-job-template: job-template.yaml
```

#### Configuring `job-template.yaml`

To enable automatic retries at the Kubernetes Job level, you must provide a template file named `job-template.yaml` inside the same profile directory (e.g., `~/.swa/profiles/k3s-s3/job-template.yaml`).

Create the file with the following content:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  generateName: snakejob-
spec:
  template:
    spec:
      containers:
      - name: snakemake
  # This allows the Pod to retry within the same Job before failing
  backoffLimit: 3
```

### 6. Monitor Workflow Progress
Poll the status of your submitted job:
```bash
curl http://localhost:8082/workflow-processes/{job_id}
```
Status can be `accepted`, `running`, `completed`, or `failed`.

Detailed troubleshooting can be found in the [Troubleshooting Guide](TROUBLESHOOTING.md).

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