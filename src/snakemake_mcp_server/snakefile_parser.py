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
    if callable(val):
        # Check for callable objects first to handle functions, lambdas, etc.
        return "<callable>"
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if isinstance(val, (list, set, tuple)):
        # For iterable objects
        return [_value_serializer(v) for v in val]
    if hasattr(val, '_plainstrings'):
        # For Namedlist objects like InputFiles, OutputFiles, etc.
        try:
            return val._plainstrings()
        except:
            # If _plainstrings() fails, return it as a string representation
            return str(val)
    if isinstance(val, dict) or hasattr(val, 'items'):
        # For dict-like objects
        try:
            return {str(k): _value_serializer(v) for k, v in val.items()}
        except:
            # If dict conversion fails, return string representation
            return str(val)
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

    # Store original sys.path and cwd
    original_sys_path = sys.path[:]
    original_cwd = os.getcwd()

    try:
        # Use the new Snakemake API which should avoid circular import issues
        from snakemake.api import SnakemakeApi
        from snakemake.settings.types import ConfigSettings, ResourceSettings, WorkflowSettings, StorageSettings, \
            DeploymentSettings, OutputSettings

        workdir = Path(snakefile_path).parent
        os.chdir(workdir)

        # Use relative path for snakefile since we're in the workdir
        relative_snakefile_path = Path(Path(snakefile_path).name)

        # Use the API to load the workflow without executing it
        config_settings = ConfigSettings()
        resource_settings = ResourceSettings()
        workflow_settings = WorkflowSettings()
        storage_settings = StorageSettings()
        deployment_settings = DeploymentSettings()

        # Create API instance and workflow in a with statement
        output_settings = OutputSettings(quiet=True)
        with SnakemakeApi(output_settings=output_settings) as api:
            workflow_api = api.workflow(
                resource_settings=resource_settings,
                config_settings=config_settings,
                workflow_settings=workflow_settings,
                storage_settings=storage_settings,
                deployment_settings=deployment_settings,
                snakefile=relative_snakefile_path,  # Use relative path since we're in the workdir
                workdir=Path.cwd()  # Use current working directory
            )

            # Access the internal workflow object to extract rule information
            internal_workflow = workflow_api._workflow

            # Extract information from each rule
            parsed_rules = []
            for rule in internal_workflow.rules:
                rule_dict = {}
                # Extract only the attributes that are relevant for API calls
                # These are the attributes that directly map to SnakemakeWrapperRequest fields
                attributes_to_extract = [
                    'name', 'input', 'output', 'params', 'resources', 
                    'priority', 'log', 'benchmark', 'conda_env', 'container_img',
                    'env_modules', 'group', 'shadow_depth', 'wrapper'
                ]

                for attr in attributes_to_extract:
                    # Try to access the attribute directly first, then with underscore prefix
                    attr_private = f"_{attr}"
                    if hasattr(rule, attr):
                        val = getattr(rule, attr)
                    elif hasattr(rule, attr_private):
                        val = getattr(rule, attr_private)
                    else:
                        continue

                    if hasattr(val, '__call__'):  # Check if it's a callable
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
        import traceback
        traceback.print_exc(file=sys.stderr)
        # Instead of returning empty, try a more basic parsing approach for demos
        # by just checking if there's a wrapper attribute in the file
        print(f"Attempting fallback parsing for {snakefile_path}", file=sys.stderr)
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
