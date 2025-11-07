import os
import sys
import logging
from pathlib import Path
from typing import Union, Dict, List, Optional
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

logger = logging.getLogger(__name__)

def run_wrapper(
    # Align with Snakemake Rule properties
    wrapper_name: str,
    wrappers_path: str,
    inputs: Optional[Union[Dict, List]] = None,
    outputs: Optional[Union[Dict, List]] = None,
    params: Optional[Dict] = None,
    log: Optional[Union[Dict, List]] = None,
    threads: int = 1,
    resources: Optional[Dict] = None,
    priority: int = 0,
    shadow_depth: Optional[str] = None,
    benchmark: Optional[str] = None,
    conda_env: Optional[str] = None,
    container_img: Optional[str] = None,
    env_modules: Optional[List[str]] = None,
    group: Optional[str] = None,
    # Execution control
    workdir: Optional[str] = None,
    timeout: int = 600,
) -> Dict:
    """
    Executes a single Snakemake wrapper by programmatically building a workflow in memory.
    """
    # Snakemake API imports (moved inside function to avoid circular imports)
    from snakemake.workflow import Workflow
    from snakemake.settings.types import (
        ConfigSettings, ResourceSettings, WorkflowSettings, StorageSettings,
        DeploymentSettings, ExecutionSettings, SchedulingSettings, OutputSettings, DAGSettings
    )
    from snakemake.executors.local import Executor as LocalExecutor
    from snakemake.executors import ExecutorSettings as LocalExecutorSettings
    from snakemake.scheduler import Greeduler as GreedyScheduler
    from snakemake.exceptions import WorkflowError, print_exception
    from snakemake.deployment.env_modules import EnvModules

    stdout_capture = StringIO()
    stderr_capture = StringIO()
    original_cwd = os.getcwd()

    try:
        # 1. Prepare working directory
        if workdir:
            execution_workdir = Path(workdir).resolve()
            os.makedirs(execution_workdir, exist_ok=True)
        else:
            import tempfile
            execution_workdir = Path(tempfile.mkdtemp(prefix="snakemake-wrapper-run-"))
        os.chdir(execution_workdir)

        # 2. Instantiate Workflow object
        workflow = Workflow(
            config_settings=ConfigSettings(),
            resource_settings=ResourceSettings(),
            workflow_settings=WorkflowSettings(),
            storage_settings=StorageSettings(),
            deployment_settings=DeploymentSettings(),
            execution_settings=ExecutionSettings(),
            scheduling_settings=SchedulingSettings(),
            output_settings=OutputSettings(),
            dag_settings=DAGSettings(),
        )
        workflow.overwrite_workdir = execution_workdir

        # 3. Add and populate a single rule in memory
        rule = workflow.add_rule("run_single_wrapper")

        if isinstance(inputs, dict):
            rule.set_input(**inputs)
        elif isinstance(inputs, list):
            rule.set_input(*inputs)

        if isinstance(outputs, dict):
            rule.set_output(**outputs)
        elif isinstance(outputs, list):
            rule.set_output(*outputs)
        else:
            raise ValueError("'outputs' must be provided.")

        if params:
            rule.set_params(**params)
        if log:
            if isinstance(log, dict):
                rule.set_log(**log)
            else:
                rule.set_log(*log)
        
        rule.resources = resources or {}
        rule.resources["_cores"] = threads
        rule.priority = priority
        rule.shadow_depth = shadow_depth
        if benchmark:
            rule.benchmark = benchmark
        if conda_env:
            rule.conda_env = conda_env
        if container_img:
            rule.container_img = container_img
        if env_modules:
            rule.env_modules = EnvModules(*env_modules)
        if group:
            rule.group = group

        wrapper_path = Path(wrappers_path) / wrapper_name
        if not wrapper_path.exists():
            raise FileNotFoundError(f"Wrapper not found at: {wrapper_path}")
        rule.wrapper = f"file://{wrapper_path.resolve()}"

        # 4. Set execution targets
        target_files = list(outputs.values()) if isinstance(outputs, dict) else outputs
        workflow.dag_settings.targets = target_files

        # 5. Execute the workflow in memory
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            log_capture = StringIO()
            stream_handler = logging.StreamHandler(log_capture)
            logging.getLogger("snakemake").addHandler(stream_handler)

            try:
                executor_plugin = LocalExecutor.get_plugin()
                scheduler_plugin = GreedyScheduler.get_plugin()
                success = workflow.execute(
                    executor_plugin=executor_plugin,
                    executor_settings=executor_plugin.settings_cls(),
                    scheduler_plugin=scheduler_plugin,
                    scheduler_settings=scheduler_plugin.settings_cls(),
                )
            finally:
                logging.getLogger("snakemake").removeHandler(stream_handler)

        final_stdout = stdout_capture.getvalue()
        final_stderr = stderr_capture.getvalue() + log_capture.getvalue()

        if success:
            return {"status": "success", "stdout": final_stdout, "stderr": final_stderr, "exit_code": 0}
        else:
            return {"status": "failed", "stdout": final_stdout, "stderr": final_stderr, "exit_code": 1, "error_message": "Workflow execution failed."}

    except Exception as e:
        stderr_val = stderr_capture.getvalue()
        exc_buffer = StringIO()
        print_exception(e, exc_buffer)
        stderr_val += exc_buffer.getvalue()
        return {"status": "failed", "stdout": stdout_capture.getvalue(), "stderr": stderr_val, "exit_code": -1, "error_message": str(e)}
    finally:
        os.chdir(original_cwd)