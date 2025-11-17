import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List
import click
import requests
from ..schemas import WrapperMetadata
from ..demo_runner import run_demo

logger = logging.getLogger(__name__)

def _load_verify_cache(cache_path: Path) -> Dict:
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not read verify cache at {cache_path}: {e}. Starting with an empty cache.")
        return {}

def _save_verify_cache(cache_path: Path, cache: Dict):
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w') as f:
            json.dump(cache, f, indent=2)
    except IOError as e:
        logger.error(f"Could not write to verify cache at {cache_path}: {e}")


@click.command(
    help="Verify all cached wrapper demos by executing them with appropriate test data."
)
@click.option("--log-level", default="INFO", type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help="Logging level. Default: INFO")
@click.option("--dry-run", is_flag=True, help="Show what would be executed without running it.")
@click.option("--by-api", default=None, help="Verify using the /tool-processes API endpoint with the specified server URL (e.g., http://127.0.0.1:8082). If not provided, will use direct demo runner.")
@click.option("--fast-fail", is_flag=True, help="Exit immediately on the first failed demo.")
@click.option("--force", is_flag=True, help="Re-run all demos, even those that previously succeeded.")
@click.option("--no-cache", is_flag=True, help="Disable reading from and writing to the cache for this run.")
@click.option("--include", multiple=True, help="Specify a wrapper to include in the verification. Can be used multiple times.")
@click.pass_context
def verify(ctx, log_level, dry_run, by_api, fast_fail, force, no_cache, include):
    """Verify all cached wrapper demos by executing them with appropriate test data."""
    # Reconfigure logging to respect the user's choice
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # This is crucial to override the initial config
    )

    wrappers_path = ctx.obj['WRAPPERS_PATH']
    logger.setLevel(log_level)

    logger.info(f"Starting verification of cached wrapper demos...")
    logger.info(f"Using wrappers from: {wrappers_path}")
    
    if by_api:
        logger.info(f"API mode enabled: using {by_api}/tool-processes endpoint for verification")

    cache_dir = Path.home() / ".swa" / "parser"
    if not cache_dir.exists():
        logger.error(f"Parser cache directory not found at: {cache_dir}. Run 'swa parse' first.")
        sys.exit(1)

    # Load verification cache
    verify_cache_path = Path.home() / ".swa" / "verify_cache.json"
    verify_cache = {} if no_cache else _load_verify_cache(verify_cache_path)
    if not no_cache:
        logger.info(f"Found {len(verify_cache)} previously successful demos in cache.")
    if force and not no_cache:
        logger.info("`--force` flag is set. All previously successful demos will be re-run.")
        verify_cache = {} # Ignore existing cache by starting with a fresh one

    # Load all cached wrapper metadata
    all_wrappers = []
    for root, _, files in os.walk(cache_dir):
        for file in files:
            if file.endswith(".json"):
                try:
                    with open(os.path.join(root, file), 'r') as f:
                        data = json.load(f)
                        all_wrappers.append(WrapperMetadata(**data))
                except Exception as e:
                    logger.error(f"Failed to load cached wrapper from {file}: {e}")
                    continue
    
    # Filter wrappers if --include is used
    if include:
        include_set = set(include)
        wrappers = [w for w in all_wrappers if w.path in include_set]
        logger.info(f"Filtered to {len(wrappers)} wrappers based on --include option.")
    else:
        wrappers = all_wrappers

    logger.info(f"Found {len(wrappers)} cached wrappers with metadata to verify.")

    # Count total demos
    total_demos = 0
    for wrapper in wrappers:
        if wrapper.demos:
            total_demos += len(wrapper.demos)

    if total_demos == 0:
        logger.warning("No demos found for the selected wrappers.")
        return

    logger.info(f"Found {total_demos} demos to verify.")

    if dry_run:
        logger.info("DRY RUN MODE: Would execute all demos but not actually run them.")
        for wrapper in wrappers:
            if wrapper.demos:
                for i, demo in enumerate(wrapper.demos):
                    demo_id = f"{wrapper.path}:{i}"
                    if not force and not no_cache and verify_cache.get(demo_id) == "success":
                        logger.info(f"  Would skip demo for wrapper (previously successful): {wrapper.path}")
                        continue
                    
                    payload = demo.payload
                    wrapper_name = payload.get('wrapper', '').replace('file://', '')
                    if wrapper_name.startswith("master/"):
                        wrapper_name = wrapper_name[len("master/"):]
                    logger.info(f"  Would execute demo for wrapper: {wrapper_name}")
        return

    # Execute all demos
    successful_demos = 0
    failed_demos = 0
    skipped_demos = 0
    first_success_wrapper = None
    first_failure_wrapper = None
    stop_execution = False
    newly_successful_demos = {}

    for wrapper in wrappers:
        if not wrapper.demos:
            continue

        logger.info(f"Verifying demos for wrapper: {wrapper.path}")
        for i, demo in enumerate(wrapper.demos):
            demo_id = f"{wrapper.path}:{i}"
            
            if not force and not no_cache and verify_cache.get(demo_id) == "success":
                logger.info(f"  - Demo {i+1}: SKIPPED (previously successful, use --force to re-run)")
                skipped_demos += 1
                continue

            payload = demo.payload
            logger.info(f"  - Processing Demo {i+1}...")
            demo_failed = False

            if by_api:
                # Use the API endpoint to execute the demo
                logger.info(f"    Demo {i+1}: Executing via API...")
                
                try:
                    # Get snakebase_dir from environment
                    snakebase_dir = os.path.expanduser(os.environ.get("SNAKEBASE_DIR", "~/snakebase"))
                    wrappers_path = os.path.join(snakebase_dir, "snakemake-wrappers")
                    demo_workdir = os.path.join(wrappers_path, wrapper.path, "test")

                    # Prepare the API payload
                    api_payload = {
                        "wrapper_name": payload.get('wrapper', '').replace('file://', '').replace('master/', ''),
                        "outputs": payload.get('output', {}),
                        "params": payload.get('params', {})
                    }

                    # Construct absolute paths for inputs
                    inputs = payload.get('input', {})
                    if isinstance(inputs, dict):
                        api_payload['inputs'] = {k: os.path.join(demo_workdir, v) for k, v in inputs.items()}
                    elif isinstance(inputs, list):
                        api_payload['inputs'] = [os.path.join(demo_workdir, v) for v in inputs]
                    else:
                        api_payload['inputs'] = inputs

                    api_url = f"{by_api.rstrip('/')}/tool-processes"
                    response = requests.post(api_url, json=api_payload)
                    
                    if response.status_code == 202:
                        job_response = response.json()
                        status_url = f"{by_api.rstrip('/')}{job_response.get('status_url')}"
                        
                        max_attempts, attempts = 30, 0
                        while attempts < max_attempts:
                            status_response = requests.get(status_url)
                            if status_response.status_code == 200:
                                status_data = status_response.json()
                                status = status_data.get('status')
                                
                                if status == 'completed':
                                    logger.info(f"    Demo {i+1}: SUCCESS (API)")
                                    successful_demos += 1
                                    if first_success_wrapper is None: first_success_wrapper = wrapper.path
                                    if not no_cache: newly_successful_demos[demo_id] = "success"
                                    break
                                elif status == 'failed':
                                    logger.error(f"    Demo {i+1}: FAILED (API)")
                                    # ... (error logging)
                                    failed_demos += 1
                                    if first_failure_wrapper is None: first_failure_wrapper = wrapper.path
                                    demo_failed = True
                                    break
                                else:
                                    time.sleep(10)
                                    attempts += 1
                            else:
                                # ... (failure logic)
                                failed_demos += 1
                                if first_failure_wrapper is None: first_failure_wrapper = wrapper.path
                                demo_failed = True
                                break
                        else: # Timeout
                            failed_demos += 1
                            if first_failure_wrapper is None: first_failure_wrapper = wrapper.path
                            demo_failed = True
                    else:
                        # ... (failure logic)
                        failed_demos += 1
                        if first_failure_wrapper is None: first_failure_wrapper = wrapper.path
                        demo_failed = True
                        
                except Exception as e:
                    # ... (failure logic)
                    failed_demos += 1
                    if first_failure_wrapper is None: first_failure_wrapper = wrapper.path
                    demo_failed = True
            else:
                # Direct demo runner logic
                wrapper_name = payload.get('wrapper', '').replace('file://', '').replace('master/', '')
                if not wrapper_name:
                    logger.warning(f"    Demo {i+1}: SKIPPED because wrapper name is empty.")
                    continue

                result = asyncio.run(run_demo(
                    wrapper_name=wrapper_name,
                    inputs=payload.get('input', {}),
                    outputs=payload.get('output', {}),
                    params=payload.get('params', {}),
                    demo_workdir=payload.get('workdir')
                ))

                if result.get("status") == "success":
                    logger.info(f"    Demo {i+1}: SUCCESS")
                    successful_demos += 1
                    if first_success_wrapper is None: first_success_wrapper = wrapper.path
                    if not no_cache: newly_successful_demos[demo_id] = "success"
                else:
                    logger.error(f"    Demo {i+1}: FAILED")
                    logger.error(f"      Exit Code: {result.get('exit_code')}")
                    logger.error(f"      Stderr: {result.get('stderr') or 'No stderr output'}")
                    failed_demos += 1
                    if first_failure_wrapper is None: first_failure_wrapper = wrapper.path
                    demo_failed = True

            if demo_failed and fast_fail:
                logger.error("Fast fail enabled. Exiting on first failure.")
                stop_execution = True
                break
        
        if stop_execution:
            break

    # Save cache if not in no-cache mode
    if not no_cache and newly_successful_demos:
        verify_cache.update(newly_successful_demos)
        _save_verify_cache(verify_cache_path, verify_cache)
        logger.info(f"Successfully updated verify cache at {verify_cache_path}")

    logger.info("="*60)
    logger.info("Verification Summary")
    logger.info(f"Successful demos: {successful_demos}")
    logger.info(f"Failed demos: {failed_demos}")
    logger.info(f"Skipped demos: {skipped_demos}")
    logger.info(f"Total demos: {total_demos}")
    if first_success_wrapper:
        logger.info(f"First successful wrapper: {first_success_wrapper}")
    if first_failure_wrapper:
        logger.info(f"First failed wrapper: {first_failure_wrapper}")
    logger.info("="*60)

    total_run = successful_demos + failed_demos
    logger.info(f"Verification completed with {failed_demos} failed demos out of {total_run} demos run.")
    if failed_demos > 0:
        logger.error(f"Verification failed with {failed_demos} demo(s) not executing successfully.")
        sys.exit(1)
    else:
        logger.info("All executed demos passed successfully!")
