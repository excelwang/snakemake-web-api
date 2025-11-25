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
from ..schemas import WrapperMetadata, DemoCall, UserWrapperRequest, PlatformRunParams
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
@click.option("--by-api", default=None, help="Verify using the /tool-processes API endpoint with the specified server URL (e.g., http://127.0.0.1:8082).")
@click.option("--fast-fail", is_flag=True, help="Exit immediately on the first failed demo.")
@click.option("--force", is_flag=True, help="Re-run all demos, even those that previously succeeded.")
@click.option("--no-cache", is_flag=True, help="Disable reading from and writing to the cache for this run.")
@click.option("--include", multiple=True, help="Specify a wrapper to include in the verification. Can be used multiple times.")
@click.pass_context
def verify(ctx, log_level, dry_run, by_api, fast_fail, force, no_cache, include):
    """Verify all cached wrapper demos by executing them with appropriate test data."""
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )

    wrappers_path_str = ctx.obj['WRAPPERS_PATH']
    logger.setLevel(log_level)
    logger.info("Starting verification process...")

    cache_dir = Path.home() / ".swa" / "parser"
    if not cache_dir.exists():
        logger.error(f"Parser cache directory not found at: {cache_dir}. Run 'swa parse' first.")
        sys.exit(1)

    verify_cache_path = Path.home() / ".swa" / "verify_cache.json"
    verify_cache = {} if no_cache else _load_verify_cache(verify_cache_path)
    if not no_cache:
        logger.info(f"Found {len(verify_cache)} previously successful demos in cache.")
    if force and not no_cache:
        logger.info("`--force` flag is set. All previously successful demos will be re-run.")
        verify_cache = {}

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
    
    if include:
        include_set = set(include)
        wrappers = [w for w in all_wrappers if w.id in include_set]
        logger.info(f"Filtered to {len(wrappers)} wrappers based on --include option.")
    else:
        wrappers = all_wrappers

    logger.info(f"Found {len(wrappers)} cached wrappers with metadata to verify.")

    if dry_run:
        logger.info("DRY RUN MODE: Would execute all demos but not actually run them.")

    successful_demos = 0
    failed_demos = 0
    skipped_demos = 0
    first_success_wrapper = None
    first_failure_wrapper = None
    stop_execution = False
    newly_successful_demos = {}
    total_demos = 0

    for wrapper in wrappers:
        demos = []
        if by_api:
            try:
                url = f"{by_api.rstrip('/')}/demos/{wrapper.id}"
                response = requests.get(url)
                response.raise_for_status()
                demos = [DemoCall(**d) for d in response.json()]
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch demos for {wrapper.id} from API: {e}")
                continue
        else:
            # Recreate the logic of the demos endpoint to read from cache
            cache_file = cache_dir / f"{wrapper.id}.json"
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    demo_data = data.get('demos', [])
                    if demo_data:
                        demos = [DemoCall(**d) for d in demo_data]

        if not demos:
            continue

        total_demos += len(demos)
        logger.info(f"Verifying {len(demos)} demos for wrapper: {wrapper.id}")

        for i, demo in enumerate(demos):
            demo_id = f"{wrapper.id}:{i}"

            if not force and not no_cache and verify_cache.get(demo_id) == "success":
                logger.info(f"  - Demo {i+1}: SKIPPED (previously successful, use --force to re-run)")
                skipped_demos += 1
                continue

            if dry_run:
                logger.info(f"  Would execute demo {i+1} for wrapper: {wrapper.id}")
                continue

            logger.info(f"  - Processing Demo {i+1}...")
            demo_failed = False

            if by_api:
                try:
                    api_url = f"{by_api.rstrip('/')}{demo.endpoint}"
                    api_payload = demo.payload.model_dump(mode="json")

                    response = requests.post(api_url, json=api_payload)

                    if response.status_code == 202:
                        job_response = response.json()
                        status_url = f"{by_api.rstrip('/')}{job_response.get('status_url')}"
                        
                        max_attempts, attempts = 60, 0 # 10 min timeout
                        while attempts < max_attempts:
                            status_response = requests.get(status_url)
                            if status_response.status_code == 200:
                                status_data = status_response.json()
                                status = status_data.get('status')
                                if status == 'completed':
                                    logger.info(f"    Demo {i+1}: SUCCESS (API)")
                                    successful_demos += 1
                                    if first_success_wrapper is None: first_success_wrapper = wrapper.id
                                    if not no_cache: newly_successful_demos[demo_id] = "success"
                                    break
                                elif status == 'failed':
                                    logger.error(f"    Demo {i+1}: FAILED (API)")
                                    result = status_data.get('result', {})
                                    logger.error(f"      Exit Code: {result.get('exit_code')}")
                                    logger.error(f"      Stderr: {result.get('stderr') or 'No stderr output'}")
                                    failed_demos += 1
                                    if first_failure_wrapper is None: first_failure_wrapper = wrapper.id
                                    demo_failed = True
                                    break
                                else:
                                    time.sleep(10)
                                    attempts += 1
                            else:
                                failed_demos += 1
                                if first_failure_wrapper is None: first_failure_wrapper = wrapper.id
                                demo_failed = True
                                break
                        else: # Timeout
                            failed_demos += 1
                            if first_failure_wrapper is None: first_failure_wrapper = wrapper.id
                            demo_failed = True
                    else:
                        logger.error(f"    Demo {i+1}: FAILED to submit job to API (HTTP {response.status_code})")
                        logger.error(f"      Response: {response.text}")
                        failed_demos += 1
                        if first_failure_wrapper is None: first_failure_wrapper = wrapper.id
                        demo_failed = True
                except Exception as e:
                    logger.error(f"    Demo {i+1}: FAILED with exception: {e}")
                    failed_demos += 1
                    if first_failure_wrapper is None: first_failure_wrapper = wrapper.id
                    demo_failed = True
            else:
                try:
                    payload = demo.payload
                    result = asyncio.run(run_demo(
                        wrapper_name=payload.wrapper_id,
                        inputs=payload.inputs,
                        outputs=payload.outputs,
                        params=payload.params,
                        demo_workdir=os.path.join(wrappers_path_str, payload.wrapper_id, "test")
                    ))
                    if result.get("status") == "success":
                        logger.info(f"    Demo {i+1}: SUCCESS")
                        successful_demos += 1
                        if first_success_wrapper is None: first_success_wrapper = wrapper.id
                        if not no_cache: newly_successful_demos[demo_id] = "success"
                    else:
                        logger.error(f"    Demo {i+1}: FAILED")
                        logger.error(f"      Exit Code: {result.get('exit_code')}")
                        logger.error(f"      Stderr: {result.get('stderr') or 'No stderr output'}")
                        failed_demos += 1
                        if first_failure_wrapper is None: first_failure_wrapper = wrapper.id
                        demo_failed = True
                except Exception as e:
                    logger.error(f"    Demo {i+1}: FAILED with exception: {e}")
                    failed_demos += 1
                    if first_failure_wrapper is None: first_failure_wrapper = wrapper.id
                    demo_failed = True

            if demo_failed and fast_fail:
                logger.error("Fast fail enabled. Exiting on first failure.")
                stop_execution = True
                break

        if stop_execution:
            break

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

