"""
Utility to convert Snakemake wrapper test Snakefiles to tool/process API calls.
Parses Snakefile content using the official Snakemake API.
"""
import os
from pathlib import Path
from typing import Dict, List, Any
import sys

def _value_serializer(val: Any) -> Any:
    """
    Serialize complex Snakemake objects to basic Python types.
    """
    if isinstance(val, (str, int, float, bool, dict, list, set, tuple)) or val is None:
        return val
    if hasattr(val, '_plainstrings'):
        # For Namedlist objects like InputFiles, OutputFiles, etc.
        return val._plainstrings()
    if isinstance(val, dict) or hasattr(val, 'items'):
        # For dict-like objects
        return {str(k): _value_serializer(v) for k, v in val.items()}
    if hasattr(val, '__iter__'):
        # For other iterables
        return [_value_serializer(v) for v in val]
    return str(val)


def parse_snakefile_with_api(snakefile_path: str) -> List[Dict[str, Any]]:
    """
    Parse a Snakefile using the official Snakemake API to extract rule information.
    
    Args:
        snakefile_path: Path to the Snakefile.
        
    Returns:
        List of rules, each as a dictionary of its attributes.
    """
    if not os.path.exists(snakefile_path):
        return []

    # Snakemake API imports (moved inside function to avoid circular imports)
    try:
        from snakemake.workflow import Workflow
        from snakemake.settings.types import (
            ConfigSettings,
            ResourceSettings,
            WorkflowSettings,
            StorageSettings,
            DeploymentSettings,
            ExecutionSettings,
            SchedulingSettings,
            OutputSettings,
            DAGSettings,
        )
        from snakemake.io import is_callable
    except ImportError as e:
        print(f"Error: Snakemake is not installed or accessible. Please install Snakemake. {e}", file=sys.stderr)
        return [] # Return empty list if Snakemake imports fail

    # Store original sys.path and cwd
    original_sys_path = sys.path[:]
    original_cwd = os.getcwd()
    workflow = None # Initialize workflow to None
    
    try:
        # 1. Instantiate Workflow object with default settings
        # We use default settings objects for parsing purposes.
        # The workdir needs to be set to the snakefile's directory for correct relative path resolution
        workdir = Path(snakefile_path).parent
        
        workflow = Workflow(
            config_settings=ConfigSettings(),
            resource_settings=ResourceSettings(),
            workflow_settings=WorkflowSettings(
                main_snakefile=snakefile_path
            ),
            storage_settings=StorageSettings(),
            deployment_settings=DeploymentSettings(),
            execution_settings=ExecutionSettings(),
            scheduling_settings=SchedulingSettings(),
            output_settings=OutputSettings(),
            dag_settings=DAGSettings(),
        )
        workflow.overwrite_workdir = workdir

        # 2. Call include() to parse the snakefile and populate the workflow object
        # This needs to be done inside the snakefile's directory
        os.chdir(workdir)
        workflow.include(snakefile_path)

        # 3. Extract information from each rule
        parsed_rules = []
        for rule in workflow.rules:
            rule_dict = {}
            # Extract all relevant attributes from the Rule object
            attributes_to_extract = [
                'name', 'docstring', 'message', 'input', 'output', 'params',
                'wildcard_constraints', 'temp_output', 'protected_output',
                'touch_output', 'shadow_depth', 'resources', 'priority', 'log',
                'benchmark', 'conda_env', 'container_img', 'is_containerized',
                'env_modules', 'group', 'wildcard_names', 'lineno', 'snakefile',
                'shellcmd', 'script', 'notebook', 'wrapper', 'template_engine',
                'cwl', 'norun', 'is_handover', 'is_checkpoint', 'restart_times'
            ]
            
            for attr in attributes_to_extract:
                # Use private attributes for some properties
                attr_private = f"_{attr}"
                if hasattr(rule, attr):
                    val = getattr(rule, attr)
                elif hasattr(rule, attr_private):
                    val = getattr(rule, attr_private)
                else:
                    continue

                if is_callable(val):
                    rule_dict[attr] = "<callable>"
                else:
                    rule_dict[attr] = _value_serializer(val)

            # Special handling for threads, which is inside resources
            if 'resources' in rule_dict and isinstance(rule_dict['resources'], dict) and '_cores' in rule_dict['resources']:
                rule_dict['threads'] = rule_dict['resources']['_cores']

            parsed_rules.append(rule_dict)
            
        return parsed_rules

    except Exception as e:
        print(f"Error parsing Snakefile with API: {e}", file=sys.stderr)
        return []
    finally:
        # Restore original working directory and sys.path
        os.chdir(original_cwd) # Always restore to original_cwd
        sys.path = original_sys_path


def generate_demo_calls_for_wrapper(wrapper_path: str) -> List[Dict[str, Any]]:
    """
    Generate demo tool/process calls for a wrapper by analyzing its test Snakefile.
    
    Args:
        wrapper_path: Path to the wrapper directory
        
    Returns:
        List of demo payloads.
    """
    test_dir = Path(wrapper_path) / "test"
    snakefile = test_dir / "Snakefile"
    
    if not snakefile.exists():
        return []
    
    # Use the new API-based parser
    parsed_rules = parse_snakefile_with_api(str(snakefile))
    
    demo_calls = []
    for rule_info in parsed_rules:
        # We only care about rules that define a wrapper for the demo
        if not rule_info.get('wrapper'):
            continue

        # The payload for the demo is the full, unmodified rule dictionary
        payload = rule_info
        
        # Add the workdir, as it's essential for execution
        payload['workdir'] = str(test_dir)
        
        demo_calls.append(payload)
        
    return demo_calls
