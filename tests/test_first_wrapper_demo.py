"""
A direct logic integration test for wrapper execution.

This test loads cached wrapper metadata and executes demos using run_demo.
If the cache directory doesn't exist, it will run the parsing command first.
"""
import pytest
import asyncio
import logging
import os
import json
import subprocess
from pathlib import Path
from snakemake_mcp_server.schemas import WrapperMetadata


def ensure_parser_cache_exists(wrappers_path_str: str):
    """
    Ensure the parser cache exists by running the parse command if needed.
    """
    # The cache is stored in ~/.swa/parser, not in the wrappers directory itself
    cache_dir = Path.home() / ".swa" / "parser"
    if not cache_dir.exists():
        logging.info(f"Parser cache directory not found at '{cache_dir}'. Running 'swa parse' command...")
        
        # Get the SNAKEBASE_DIR from environment variable
        snakebase_dir = os.path.expanduser(os.environ.get("SNAKEBASE_DIR", "~/snakebase"))
        
        # Run the swa parse command
        try:
            result = subprocess.run(
                ["swa", "parse"],
                env={**os.environ, "SNAKEBASE_DIR": snakebase_dir},
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                logging.info("Successfully generated parser cache with 'swa parse' command.")
            else:
                logging.error(f"Failed to generate parser cache: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            logging.error("Generating parser cache timed out after 5 minutes.")
            return False
        except FileNotFoundError:
            logging.error("'swa' command not found. Please ensure snakemake-web-api is installed.")
            return False
        except Exception as e:
            logging.error(f"Error running 'swa parse' command: {e}")
            return False

    return True


def load_cached_wrapper_metadata(wrappers_dir: str) -> list[WrapperMetadata]:
    """
    Loads cached metadata for all wrappers from the pre-parsed cache.
    If the cache doesn't exist, it will be generated first.
    """
    if not ensure_parser_cache_exists(wrappers_dir):
        logging.warning(f"Could not generate parser cache directory. No tools will be loaded.")
        return []

    # Cache is stored in ~/.swa/parser, not relative to the wrappers directory
    cache_dir = Path.home() / ".swa" / "parser"
    if not cache_dir.exists():
        logging.warning(f"Parser cache directory still not found at '{cache_dir}'. No tools will be loaded.")
        return []

    wrappers = []
    for root, _, files in os.walk(cache_dir):
        for file in files:
            if file.endswith(".json"):
                try:
                    with open(os.path.join(root, file), 'r') as f:
                        data = json.load(f)
                        wrappers.append(WrapperMetadata(**data))
                except Exception as e:
                    logging.error(f"Failed to load cached wrapper from {file}: {e}")
    return wrappers


@pytest.mark.asyncio
async def test_first_wrapper_demo():
    """
    Tests the first cached wrapper demo using run_demo function directly.
    """
    # Use the environment variable to get the snakebase directory
    snakebase_dir = os.path.expanduser(os.environ.get("SNAKEBASE_DIR", "~/snakebase"))
    wrappers_path = os.path.join(snakebase_dir, "snakemake-wrappers")
    
    logging.info(f"Starting test for first cached wrapper demo from: {wrappers_path}")

    wrappers = load_cached_wrapper_metadata(wrappers_path)
    if not wrappers:
        pytest.skip("No cached wrappers found, skipping cached demo test.")

    logging.info(f"Found {len(wrappers)} cached wrappers. Testing first demo...")

    successful_demos = 0
    failed_demos = 0
    skipped_demos = 0

    # Find and execute only the first demo found among all wrappers
    first_demo_executed = False
    for wrapper in wrappers:
        if first_demo_executed:
            break
            
        if not wrapper.demos:
            continue

        logging.info(f"Testing demos for wrapper: {wrapper.path}")
        for i, demo in enumerate(wrapper.demos):
            if first_demo_executed:
                break

            payload = demo.payload
            logging.info(f"  - Processing Demo {i+1}...")

            # Only use the 4 required parameters for the API
            wrapper_name = payload.get('wrapper', '').replace('file://', '')
            if wrapper_name.startswith("master/"):
                wrapper_name = wrapper_name[len("master/"):]

            inputs = payload.get('input', {})
            outputs = payload.get('output', {})
            params = payload.get('params', {})

            # Skip if wrapper name is empty
            if not wrapper_name:
                logging.warning(f"    Demo {i+1}: SKIPPED because wrapper name is empty.")
                skipped_demos += 1
                # Continue to the next demo even if this one is skipped
                continue


            # Execute the wrapper using run_demo which handles input file copying
            logging.info(f"    Demo {i+1}: Executing demo...")
            demo_workdir = payload.get('workdir')
            from snakemake_mcp_server.demo_runner import run_demo
            result = await run_demo(
                wrapper_name=wrapper_name,
                inputs=inputs,
                outputs=outputs,
                params=params,
                demo_workdir=demo_workdir  # Pass the demo workdir for input file copying
            )

            if result.get("status") == "success":
                logging.info(f"    Demo {i+1}: SUCCESS")
                successful_demos += 1
            else:
                logging.error(f"    Demo {i+1}: FAILED")
                logging.error(f"      Exit Code: {result.get('exit_code')}")
                logging.error(f"      Stderr: {result.get('stderr')}")
                failed_demos += 1

            # Mark that we've executed the first demo and break out of loops
            first_demo_executed = True
            break  # Break out of the inner loop

        if first_demo_executed:
            break  # Break out of the outer loop

    logging.info("="*60)
    logging.info("Cached Demo Test Summary")
    logging.info(f"Successful demos: {successful_demos}")
    logging.info(f"Failed demos: {failed_demos}")
    logging.info(f"Skipped demos: {skipped_demos}")
    logging.info("="*60)

    # If the demo failed, the test should fail
    if failed_demos > 0:
        pytest.fail(f"Test failed because the first demo did not execute successfully.")
    
    logging.info(f"Test completed with {failed_demos} failed demos out of {successful_demos + failed_demos + skipped_demos} total demos.")