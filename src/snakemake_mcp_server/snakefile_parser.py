"""
Utility to convert Snakemake wrapper test Snakefiles to tool/process API calls.
Parses Snakefile content using the official Snakemake API and its DAG.
"""
import os
from pathlib import Path
from typing import Dict, List, Any, Tuple, Set
import sys

def _value_serializer(val: Any) -> Any:
    """
    Serialize complex Snakemake objects to basic Python types.
    """
    if callable(val):
        return "<callable>"
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if isinstance(val, (list, set, tuple)):
        return [_value_serializer(v) for v in val]
    if hasattr(val, '_plainstrings'):
        try:
            return val._plainstrings()
        except:
            return str(val)
    if isinstance(val, dict) or hasattr(val, 'items'):
        try:
            return {str(k): _value_serializer(v) for k, v in val.items()}
        except:
            return str(val)
    return str(val)


def parse_snakefile_with_api(snakefile_path: str) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """
    Parse a Snakefile using the Snakemake API to extract rule information
    and identify leaf rules from the DAG.

    Args:
        snakefile_path: Path to the Snakefile.

    Returns:
        A tuple containing:
        - A list of all parsed rules as dictionaries.
        - A set of names of the leaf rules (rules with no dependencies).
    """
    if not os.path.exists(snakefile_path):
        return [], set()

    original_sys_path = sys.path[:]
    original_cwd = os.getcwd()

    try:
        from snakemake.api import SnakemakeApi
        from snakemake.settings.types import ConfigSettings, ResourceSettings, WorkflowSettings, StorageSettings, \
            DeploymentSettings, OutputSettings
        from snakemake.logging import Quietness

        workdir = Path(snakefile_path).parent
        os.chdir(workdir)
        relative_snakefile_path = Path(Path(snakefile_path).name)

        config_settings = ConfigSettings()
        resource_settings = ResourceSettings()
        workflow_settings = WorkflowSettings()
        storage_settings = StorageSettings()
        deployment_settings = DeploymentSettings()
        # Use the correct quietness setting (iterable enum)
        output_settings = OutputSettings(quiet=[Quietness.ALL])

        with SnakemakeApi(output_settings=output_settings) as api:
            workflow_api = api.workflow(
                resource_settings=resource_settings,
                config_settings=config_settings,
                workflow_settings=workflow_settings,
                storage_settings=storage_settings,
                deployment_settings=deployment_settings,
                snakefile=relative_snakefile_path,
                workdir=Path.cwd()
            )
            internal_workflow = workflow_api._workflow

            # The DAG is only built if there is a target. If not, dag is None.
            if internal_workflow.dag is None:
                return [], set()

            # 1. Identify leaf rules from the DAG
            leaf_rule_names = {job.rule.name for job in internal_workflow.dag.leaves()}

            # 2. Extract information from all rules
            parsed_rules = []
            for rule in internal_workflow.rules:
                rule_dict = {}
                attributes_to_extract = [
                    'name', 'input', 'output', 'params', 'resources', 
                    'priority', 'log', 'benchmark', 'conda_env', 'container_img',
                    'env_modules', 'group', 'shadow_depth', 'wrapper'
                ]
                for attr in attributes_to_extract:
                    attr_private = f"_{attr}"
                    if hasattr(rule, attr):
                        val = getattr(rule, attr)
                    elif hasattr(rule, attr_private):
                        val = getattr(rule, attr_private)
                    else:
                        continue
                    
                    rule_dict[attr] = _value_serializer(val)

                if 'resources' in rule_dict and isinstance(rule_dict['resources'], dict) and '_cores' in rule_dict['resources']:
                    rule_dict['threads'] = rule_dict['resources']['_cores']
                
                parsed_rules.append(rule_dict)

            return parsed_rules, leaf_rule_names

    except Exception as e:
        print(f"Error parsing Snakefile with API: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return [], set()
    finally:
        os.chdir(original_cwd)
        sys.path = original_sys_path


def generate_demo_calls_for_wrapper(wrapper_path: str) -> List[Dict[str, Any]]:
    """
    Generate demo calls for a wrapper by analyzing its test Snakefile's DAG
    to find executable leaf rules that point to the correct wrapper.
    """
    test_dir = Path(wrapper_path) / "test"
    snakefile = test_dir / "Snakefile"

    if not snakefile.exists():
        return []

    parsed_rules, leaf_rule_names = parse_snakefile_with_api(str(snakefile))

    if not parsed_rules or not leaf_rule_names:
        return []

    demo_calls = []
    current_wrapper_path = Path(wrapper_path).resolve()

    for rule_info in parsed_rules:
        wrapper_directive = rule_info.get("wrapper", "")
        if not wrapper_directive:
            continue

        # A rule is a valid demo if it meets three criteria:
        # 1. It is a leaf rule in the DAG.
        # 2. It has a 'wrapper' directive.
        # 3. The wrapper directive resolves to the path of the wrapper being processed.
        
        is_leaf = rule_info.get("name") in leaf_rule_names
        
        # Resolve the path of the wrapper called in the rule and compare it
        rule_wrapper_path = (test_dir / wrapper_directive).resolve()
        is_correct_wrapper = (rule_wrapper_path == current_wrapper_path)

        if is_leaf and is_correct_wrapper:
            payload = rule_info
            payload['workdir'] = str(test_dir)
            demo_calls.append(payload)

    return demo_calls
