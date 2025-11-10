"""
A direct logic integration test for wrapper execution.

This test bypasses the HTTP API layer to directly call the underlying business
logic for parsing and running all available wrapper demos. It ensures the core
functionality of run_wrapper and parameter processing is correct.
"""
import pytest
import asyncio
import logging
import os
import yaml
from pathlib import Path

# Add src to path to allow direct imports of app logic
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from snakemake_mcp_server.wrapper_runner import run_wrapper
from snakemake_mcp_server.snakefile_parser import generate_demo_calls_for_wrapper
from snakemake_mcp_server.fastapi_app import WrapperMetadata, DemoCall

# Helper functions for payload transformation
def _value_is_valid(value):
    if value is None: return False
    if isinstance(value, str) and value in ("<callable>",): return False
    if isinstance(value, list) and len(value) == 0: return False
    if isinstance(value, dict) and len(value) == 0: return False
    return True

def _convert_snakemake_io(io_value):
    if isinstance(io_value, dict): return {k: v for k, v in io_value.items() if _value_is_valid(v)}
    elif isinstance(io_value, (list, tuple)): return [v for v in io_value if _value_is_valid(v)]
    elif _value_is_valid(io_value): return [io_value]
    else: return []

def _convert_snakemake_params(params_value):
    if isinstance(params_value, dict): return {k: v for k, v in params_value.items() if _value_is_valid(v)}
    elif isinstance(params_value, (list, tuple)):
        result = {}
        for idx, val in enumerate(params_value):
            if _value_is_valid(val): result[f'param_{idx}'] = val
        return result
    elif _value_is_valid(params_value): return params_value
    else: return {}

def load_all_wrapper_metadata(wrappers_dir: str) -> list[WrapperMetadata]:
    """
    Loads metadata for all wrappers by scanning for meta.yaml files.
    This is a standalone version of the function in fastapi_app.py for direct use in tests.
    """
    wrappers = []
    for root, dirs, files in os.walk(wrappers_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        if "meta.yaml" in files:
            meta_file_path = os.path.join(root, "meta.yaml")
            try:
                with open(meta_file_path, 'r', encoding='utf-8') as f:
                    meta_data = yaml.safe_load(f)
                
                wrapper_path = os.path.relpath(root, wrappers_dir)
                
                basic_demo_calls = generate_demo_calls_for_wrapper(root)
                enhanced_demos = [
                    DemoCall(method='POST', endpoint='/tool-processes', payload=call)
                    for call in basic_demo_calls
                ] if basic_demo_calls else None

                wrappers.append(WrapperMetadata(
                    name=meta_data.get('name', os.path.basename(root)),
                    path=wrapper_path,
                    demos=enhanced_demos,
                    **meta_data
                ))
            except Exception as e:
                logging.warning(f"Could not load meta.yaml from {meta_file_path}: {e}")
                continue
    return wrappers

@pytest.mark.asyncio
async def test_all_demos_direct_logic():
    """
    Tests the core logic by finding all demos and executing them via run_wrapper.
    """
    wrappers_path = "./snakebase/snakemake-wrappers"
    logging.info("Starting direct logic test for all wrapper demos...")

    wrappers = load_all_wrapper_metadata(wrappers_path)
    if not wrappers:
        pytest.skip("No wrappers found, skipping direct logic test.")

    logging.info(f"Found {len(wrappers)} wrappers. Testing all demos directly.")

    successful_demos = 0
    failed_demos = 0
    skipped_demos = 0

    for wrapper in wrappers:
        if not wrapper.demos:
            continue

        logging.info(f"Testing wrapper: {wrapper.path}")
        for i, demo in enumerate(wrapper.demos):
            payload = demo.payload
            logging.info(f"  - Processing Demo {i+1}...")

            # Skip demos with non-static (callable) parameters as they cannot be executed directly
            if '<callable>' in str(payload):
                logging.warning(f"    Demo {i+1}: SKIPPED because it contains non-static (callable) parameters.")
                skipped_demos += 1
                continue

            try:
                # Prepare the arguments for run_wrapper from the demo payload
                api_payload = { "wrapper_name": payload.get('wrapper', '').replace('file://', '') }
                if 'input' in payload and _value_is_valid(payload['input']): api_payload['inputs'] = _convert_snakemake_io(payload['input'])
                if 'output' in payload and _value_is_valid(payload['output']): api_payload['outputs'] = _convert_snakemake_io(payload['output'])
                if 'params' in payload and _value_is_valid(payload['params']): api_payload['params'] = _convert_snakemake_params(payload['params'])
                if 'log' in payload and _value_is_valid(payload['log']): api_payload['log'] = _convert_snakemake_io(payload['log'])
                if 'threads' in payload: api_payload['threads'] = payload['threads']
                elif 'resources' in payload and '_cores' in payload['resources']: api_payload['threads'] = payload['resources']['_cores']
                if 'workdir' in payload and payload['workdir'] is not None: api_payload['workdir'] = payload['workdir']
                
                # Directly call the core execution logic
                logging.info(f"    Demo {i+1}: Executing...")
                result = await run_wrapper(wrappers_path=wrappers_path, **api_payload)

                if result.get("status") == "success":
                    logging.info(f"    Demo {i+1}: SUCCESS")
                    successful_demos += 1
                else:
                    logging.error(f"    Demo {i+1}: FAILED")
                    logging.error(f"      Exit Code: {result.get('exit_code')}")
                    logging.error(f"      Stderr: {result.get('stderr')}")
                    failed_demos += 1

            except Exception as e:
                logging.error(f"    Demo {i+1}: EXCEPTION during execution: {e}", exc_info=True)
                failed_demos += 1

    logging.info("="*60)
    logging.info("Direct Logic Test Summary")
    logging.info(f"Successful demos: {successful_demos}")
    logging.info(f"Failed demos: {failed_demos}")
    logging.info(f"Skipped demos (non-static): {skipped_demos}")
    logging.info("="*60)

    assert failed_demos == 0, f"{failed_demos} demos failed during direct logic execution."
