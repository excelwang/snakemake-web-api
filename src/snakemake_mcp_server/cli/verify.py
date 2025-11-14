import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
import click
import requests
from ..schemas import WrapperMetadata
from ..demo_runner import run_demo

logger = logging.getLogger(__name__)

@click.command(
    help="Verify all cached wrapper demos by executing them with appropriate test data."
)
@click.option("--log-level", default="INFO", type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help="Logging level. Default: INFO")
@click.option("--dry-run", is_flag=True, help="Show what would be executed without running it.")
@click.option("--by-api", default=None, help="Verify using the /tool-processes API endpoint with the specified server URL (e.g., http://127.0.0.1:8082). If not provided, will use direct demo runner.")
@click.pass_context
def verify(ctx, log_level, dry_run, by_api):
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

    # Load all cached wrapper metadata
    wrappers = []
    for root, _, files in os.walk(cache_dir):
        for file in files:
            if file.endswith(".json"):
                try:
                    with open(os.path.join(root, file), 'r') as f:
                        data = json.load(f)
                        wrappers.append(WrapperMetadata(**data))
                except Exception as e:
                    logger.error(f"Failed to load cached wrapper from {file}: {e}")
                    continue

    logger.info(f"Found {len(wrappers)} cached wrappers with metadata.")

    # Count total demos
    total_demos = 0
    for wrapper in wrappers:
        if wrapper.demos:
            total_demos += len(wrapper.demos)

    if total_demos == 0:
        logger.warning("No demos found in cached wrapper metadata.")
        return

    logger.info(f"Found {total_demos} demos to verify.")

    if dry_run:
        logger.info("DRY RUN MODE: Would execute all demos but not actually run them.")
        for wrapper in wrappers:
            if wrapper.demos:
                for demo in wrapper.demos:
                    payload = demo.payload
                    wrapper_name = payload.get('wrapper', '').replace('file://', '')
                    if wrapper_name.startswith("master/"):
                        wrapper_name = wrapper_name[len("master/"):]
                    logger.info(f"  Would execute demo for wrapper: {wrapper_name}")
        return

    # Execute all demos
    successful_demos = 0
    failed_demos = 0

    for wrapper in wrappers:
        if not wrapper.demos:
            continue

        logger.info(f"Verifying demos for wrapper: {wrapper.path}")
        for i, demo in enumerate(wrapper.demos):
            payload = demo.payload
            logger.info(f"  - Processing Demo {i+1}...")

            if by_api:
                # Use the API endpoint to execute the demo
                logger.info(f"    Demo {i+1}: Executing via API...")
                
                try:
                    # Get snakebase_dir from environment
                    snakebase_dir = os.path.expanduser(os.environ.get("SNAKEBASE_DIR", "~/snakebase"))
                    wrappers_path = os.path.join(snakebase_dir, "snakemake-wrappers")
                    demo_workdir = os.path.join(wrappers_path, wrapper.path, "test")

                    # Prepare the API payload by using only the fields that are compatible with the API
                    # The API expects: wrapper_name, inputs, outputs, params
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

                    # Make request to the API endpoint
                    api_url = f"{by_api.rstrip('/')}/tool-processes"
                    
                    response = requests.post(api_url, json=api_payload)
                    
                    if response.status_code == 202:  # Accepted
                        # Get job ID from response
                        job_response = response.json()
                        job_id = job_response.get('job_id')
                        
                        # Poll for job status
                        status_url = f"{by_api.rstrip('/')}{job_response.get('status_url')}"
                        
                        # Wait for job completion (with timeout)
                        max_attempts = 30  # 5 min timeout if each poll waits 10 seconds
                        attempts = 0
                        
                        while attempts < max_attempts:
                            status_response = requests.get(status_url)
                            
                            if status_response.status_code == 200:
                                status_data = status_response.json()
                                status = status_data.get('status')
                                
                                if status == 'completed':
                                    logger.info(f"    Demo {i+1}: SUCCESS (API)")
                                    successful_demos += 1
                                    break
                                elif status == 'failed':
                                    logger.error(f"    Demo {i+1}: FAILED (API)")
                                    result = status_data.get('result', {})
                                    logger.error(f"      Exit Code: {result.get('exit_code')}")
                                    logger.error(f"      Stderr: {result.get('stderr') or 'No stderr output'}")
                                    failed_demos += 1
                                    break
                                else:
                                    # Still running, wait before polling again
                                    logger.debug(f"      Job status: {status}, waiting...")
                                    time.sleep(10)  # Wait 10 seconds before polling again
                                    attempts += 1
                                    # Check again on the next iteration
                            else:
                                logger.error(f"    Demo {i+1}: FAILED to get job status (HTTP {status_response.status_code})")
                                failed_demos += 1
                                break
                        else:
                            # Timeout reached
                            logger.error(f"    Demo {i+1}: TIMEOUT waiting for job completion")
                            failed_demos += 1
                    else:
                        logger.error(f"    Demo {i+1}: FAILED to submit job to API (HTTP {response.status_code})")
                        logger.error(f"      Response: {response.text}")
                        failed_demos += 1
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"    Demo {i+1}: FAILED due to connection error: {e}")
                    failed_demos += 1
                except Exception as e:
                    logger.error(f"    Demo {i+1}: FAILED with exception: {e}")
                    failed_demos += 1
            else:
                # Use the original logic (direct demo runner)
                wrapper_name = payload.get('wrapper', '').replace('file://', '')
                if wrapper_name.startswith("master/"):
                    wrapper_name = wrapper_name[len("master/"):]

                inputs = payload.get('input', {})
                outputs = payload.get('output', {})
                params = payload.get('params', {})

                # Skip if wrapper name is empty
                if not wrapper_name:
                    logger.warning(f"    Demo {i+1}: SKIPPED because wrapper name is empty.")
                    continue

                # Execute the wrapper using run_demo which handles input file copying
                logger.info(f"    Demo {i+1}: Executing demo...")
                demo_workdir = payload.get('workdir')
                result = asyncio.run(run_demo(
                    wrapper_name=wrapper_name,
                    inputs=inputs,
                    outputs=outputs,
                    params=params,
                    demo_workdir=demo_workdir  # Pass the demo workdir for input file copying
                ))

                if result.get("status") == "success":
                    logger.info(f"    Demo {i+1}: SUCCESS")
                    successful_demos += 1
                else:
                    logger.error(f"    Demo {i+1}: FAILED")
                    logger.error(f"      Exit Code: {result.get('exit_code')}")
                    logger.error(f"      Stderr: {result.get('stderr') or 'No stderr output'}")
                    failed_demos += 1

    logger.info("="*60)
    logger.info("Verification Summary")
    logger.info(f"Successful demos: {successful_demos}")
    logger.info(f"Failed demos: {failed_demos}")
    logger.info(f"Total demos: {successful_demos + failed_demos}")
    logger.info("="*60)

    logger.info(f"Verification completed with {failed_demos} failed demos out of {successful_demos + failed_demos} total demos.")
    if failed_demos > 0:
        logger.error(f"Verification failed with {failed_demos} demo(s) not executing successfully.")
        sys.exit(1)
    else:
        logger.info("All demos executed successfully!")
