"""
Utility to convert Snakemake wrapper test Snakefiles to tool/process API calls.
Parses Snakefile content using the official Snakemake API and its DAG.
"""
import os
from pathlib import Path
from typing import Dict, List, Any, Tuple, Set
import sys
import tempfile
import logging
# from snakemake.io import Params # Explicitly import Params - REMOVED to avoid NameError

logger = logging.getLogger(__name__)

# logger.debug(f"ID of imported Params class: {id(Params)}") # REMOVED

def _value_serializer(val: Any) -> Any:
    """
    Serialize complex Snakemake objects to basic Python types.
    """
    # 1. Handle Params, which is a special Namedlist that must be treated as a dict.
    if type(val).__name__ == 'Params':
        logger.debug(f"Serializing Snakemake Params object: type={type(val)}, value={val}")
        if hasattr(val, '_get_names'):
            params_dict = {}
            for name, (index, _) in list(val._get_names()):
                try:
                    params_dict[name] = _value_serializer(val[index])
                except Exception as e:
                    logger.debug(f"  Error getting parameter '{name}' at index {index}: {e}")
            return params_dict
        else:
            return str(val)

    # 2. Handle Namedlists with named items (which act as dicts).
    # This MUST come before the generic list check.
    if hasattr(val, '_names') and val._names:
        logger.debug(f"Serializing Namedlist with names: {val._names}")
        return {name: _value_serializer(val[index_tuple[0]]) for name, index_tuple in val._names.items()}

    # 3. Handle all other list-like objects (including Namedlists without names).
    if isinstance(val, (list, set, tuple)):
        return [_value_serializer(v) for v in val]

    # 4. Handle single file objects (IOFile) that are not lists.
    if hasattr(val, 'is_directory'):
        if val.is_directory:
            return {'path': str(val), 'is_directory': True}
        return str(val)

    # 5. Handle primitive and other specific types.
    if isinstance(val, Path):
        return str(val)
    if callable(val):
        return "<callable>"
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if isinstance(val, dict) or hasattr(val, 'items'):
        try:
            return {str(k): _value_serializer(v) for k, v in val.items()}
        except:
            return str(val)
            
    # 6. Fallback for any other objects.
    if hasattr(val, '__dict__'):
        try:
            result = {}
            for attr_name, attr_value in val.__dict__.items():
                if not attr_name.startswith('_'):
                    result[attr_name] = _value_serializer(attr_value)
            if result:
                return result
        except:
            pass
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
        from snakemake.settings.enums import Quietness

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

            leaf_rule_names = set()
            # The DAG is only built if there is a target. If not, dag is None.
            if internal_workflow.dag is not None:
                leaf_rule_names = {job.rule.name for job in internal_workflow.dag.leaves()}

            # Extract information from all rules
            parsed_rules = []
            for rule in internal_workflow.rules:
                rule_dict = {}
                attributes_to_extract = [
                    'name', 'input', 'output', 'params', 'resources', 
                    'priority', 'log', 'benchmark', 'conda_env', 'container_img',
                    'env_modules', 'group', 'shadow_depth', 'wrapper'
                ]
                for attr in attributes_to_extract:
                    val = None
                    attr_private = f"_{attr}"
                    if hasattr(rule, attr):
                        val = getattr(rule, attr)
                    elif hasattr(rule, attr_private):
                        val = getattr(rule, attr_private) # Corrected this line
                    
                    if attr == 'params': # Specific logging for params
                        logger.debug(f"Before serialization - rule.params: type={type(val)}, value={val}")

                    if val is not None:
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


def _has_wildcards(data: Any) -> bool:
    """
    Recursively check for Snakemake wildcards '{...}' in a data structure.
    """
    if isinstance(data, str):
        if '{' in data and '}' in data:
            return True
    elif isinstance(data, dict):
        for value in data.values():
            if _has_wildcards(value):
                return True
    elif isinstance(data, list):
        for item in data:
            if _has_wildcards(item):
                return True
    return False


def generate_demo_calls_for_wrapper(wrapper_path: str, wrappers_root: str) -> List[Dict[str, Any]]:
    """
    Generate demo calls for a wrapper by analyzing its test Snakefile's DAG
    to find executable leaf rules that point to the correct wrapper.
    """
    test_dir = Path(wrapper_path) / "test"
    snakefile = test_dir / "Snakefile"

    if not snakefile.exists():
        return []

    # Read the Snakefile content as plain text to check for meta_wrapper directive
    # This avoids triggering remote calls via Snakemake API if meta_wrapper is present
    try:
        with open(snakefile, 'r') as f:
            snakefile_content = f.read()
        if "meta_wrapper:" in snakefile_content:
            logger.debug(f"Skipping demo for wrapper '{wrapper_path}' due to 'meta_wrapper:' directive in {snakefile}")
            return []
    except Exception as e:
        logger.error(f"Error reading {snakefile} to check for meta_wrapper: {e}")
        return []

    parsed_rules, leaf_rule_names = parse_snakefile_with_api(str(snakefile))

    if not parsed_rules:
        return []

    demo_calls = []
    current_wrapper_path = Path(wrapper_path).resolve()
    wrappers_root_path = Path(wrappers_root).resolve()

    for rule_info in parsed_rules:
        wrapper_directive = rule_info.get("wrapper", "")
        if not wrapper_directive:
            continue

        # Remove 'master/' prefix if present, as per user instruction
        if wrapper_directive.startswith("master/"):
            wrapper_directive = wrapper_directive[len("master/"):]

        is_leaf = rule_info.get("name") in leaf_rule_names
        
        # Compare the wrapper directive (relative path) with the relative path of the current wrapper
        is_correct_wrapper = (Path(wrapper_directive) == current_wrapper_path.relative_to(wrappers_root_path))

        # A rule is a valid demo if it's a correct self-test AND either:
        # a) it's a leaf rule in a DAG, OR
        # b) it's the only rule in a simple Snakefile (which likely has no DAG).
        if is_correct_wrapper and (is_leaf or len(parsed_rules) == 1):
            # New validation step: check for unresolved wildcards
            if _has_wildcards(rule_info.get('input', {})) or \
               _has_wildcards(rule_info.get('output', {})):
                logger.debug(f"Skipping rule '{rule_info.get('name')}' as a demo because it has unresolved wildcards.")
                continue

            payload = rule_info
            payload['workdir'] = str(test_dir)
            demo_calls.append(payload)

    return demo_calls

def convert_rule_to_tool_process_call(rule_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a parsed Snakemake rule into a tool/process API call format.
    """
    inputs = rule_info.get('input', {})
    outputs = rule_info.get('output', {})
    params = rule_info.get('params', {})
    
    # Extract the wrapper path from the 'wrapper' directive
    wrapper_directive = rule_info.get('wrapper', '')
    if wrapper_directive.startswith("master/"):
        wrapper_name = wrapper_directive[len("master/"):]
    else:
        wrapper_name = wrapper_directive
        
    return {
        "wrapper_name": wrapper_name,
        "inputs": inputs,
        "outputs": outputs,
        "params": params,
        "log": rule_info.get('log'),
        "threads": rule_info.get('threads'),
        # Add other potential fields as needed, mapping Snakemake rule attributes to API fields
    }
