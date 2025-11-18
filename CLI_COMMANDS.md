# CLI Commands Guide

This document provides a complete reference for all command-line interface (CLI) commands available in the Snakemake Web API.

## Overview

The `snakemake-web-api` CLI tool (also available as `swa`) provides multiple subcommands for different operations. This tool is the primary interface for starting servers, parsing wrappers, and verifying functionality.

## Common Options

All subcommands support the `--snakebase-dir` option to specify the base directory for snakemake-wrappers and snakemake-workflows:

```bash
swa [subcommand] --snakebase-dir /path/to/snakebase
```

By default, the tool looks for the snakebase directory in `~/snakebase` or uses the `SNAKEBASE_DIR` environment variable if set.

## Subcommands

### `swa parse`

Parses all wrapper metadata and demos, then caches them to JSON files for faster server startup.

```bash
swa parse
```

This command:
- Walks through the `snakemake-wrappers` directory
- Extracts metadata from `meta.yaml` files
- Generates demo calls for each wrapper
- Caches the data to `~/.swa/parser/` directory
- This cache is used by both REST and MCP servers to provide wrapper information quickly

### `swa rest`

Starts the Snakemake server with native FastAPI REST endpoints. This provides standard REST API endpoints with full OpenAPI documentation.

```bash
swa rest \
    --host 127.0.0.1 \
    --port 8082 \
    --log-level INFO
```

Options:
- `--host`: Host to bind to (default: 127.0.0.1)
- `--port`: Port to bind to (default: 8082)
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR; default: INFO)

When running, this server provides:
- Standard REST API endpoints
- Interactive OpenAPI documentation at `http://[host]:[port]/docs`
- All Snakemake functionality as REST API calls

### `swa mcp`

Starts the Snakemake server with MCP (Model Context Protocol) support. This provides MCP protocol endpoints derived from FastAPI definitions.

```bash
swa mcp \
    --host 127.0.0.1 \
    --port 8083 \
    --log-level INFO
```

Options:
- `--host`: Host to bind to (default: 127.0.0.1)
- `--port`: Port to bind to (default: 8083)
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR; default: INFO)

When running, this server provides:
- MCP protocol endpoints at `http://[host]:[port]/mcp`
- MCP tools for Snakemake wrapper and workflow execution
- Compatibility with MCP-enabled clients

### `swa verify`

Verifies all cached wrapper demos by executing them with appropriate test data. This can run either directly or via the API.

```bash
swa verify \
    --log-level INFO \
    --dry-run \
    --fast-fail \
    --force
```

Options:
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR; default: INFO)
- `--dry-run`: Show what would be executed without running it
- `--by-api`: Verify using the /tool-processes API endpoint with the specified server URL (e.g., http://127.0.0.1:8082)
- `--fast-fail`: Exit immediately on the first failed demo
- `--force`: Re-run all demos, even those that previously succeeded
- `--no-cache`: Disable reading from and writing to the cache for this run
- `--include`: Specify a wrapper to include in the verification (can be used multiple times)

The verification process:
- Loads cached wrapper metadata from `~/.swa/parser/`
- Runs each demo with test data from the wrapper's test directory
- Keeps track of successful runs in a verification cache (`~/.swa/verify_cache.json`)
- Shows a summary of successful/failed demos

## Environment Variables

The following environment variables can be configured for the server:

| Variable | Purpose | Default |
|----------|---------|---------|
| `SNAKEBASE_DIR` | Base directory for `snakemake-wrappers` and `snakemake-workflows` subdirectories | `~/snakebase` |
| `SNAKEMAKE_CONDA_PREFIX` | Path to conda environments for Snakemake | `~/.snakemake/conda` |

## Configuration Files

The tool looks for a configuration file at `~/.swa/.env` on startup and loads environment variables from it if it exists.

## Directory Structure

The tool expects the `snakebase` directory to have the following structure:

```
snakebase/
├── snakemake-wrappers/
│   ├── bio/
│   ├── meta/
│   └── ...
└── snakemake-workflows/
    ├── rna-seq-star-deseq2/
    ├── dna-seq-varlociraptor/
    └── ...
```