"""
Utility to convert Snakemake wrapper test Snakefiles to tool/process API calls.
Parses Snakefile content using text parsing to extract rule information.
"""
import re
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_snakefile_content(snakefile_content: str) -> List[Dict[str, Any]]:
    """
    Parse a Snakefile and extract rule information that can be converted to tool/process API calls.
    
    Args:
        snakefile_content: Content of the Snakefile as string
        
    Returns:
        List of rules, each with input, output, params, log, wrapper information
    """
    rules = []
    
    # Split content into lines
    lines = snakefile_content.split('\n')
    
    current_rule = None
    current_section = None
    
    for line in lines:
        line = line.rstrip()  # Remove trailing whitespace
        
        # Match rule definition
        rule_match = re.match(r'^rule\s+(\w+):', line)
        if rule_match:
            # Save previous rule if exists
            if current_rule:
                rules.append(current_rule)
            
            # Start new rule
            current_rule = {
                'name': rule_match.group(1),
                'input': [],
                'output': [],
                'params': {},
                'log': [],
                'wrapper': None,
                'threads': None
            }
            continue
        
        # Skip if no current rule
        if not current_rule:
            continue
        
        # Match section start - process all valid Snakemake sections, not just API-supported ones
        section_match = re.match(r'^\s+(input|output|params|log|wrapper|threads|conda|singularity|benchmark|shadow|resources|version|localrules|message|priority|wildcard_constraints|group|benchmark_repeats|cgroup|default_target|localrule|restart_times|ruleorder):\s*(.*)$', line)
        if section_match:
            section_name = section_match.group(1)
            current_section = section_name
            # Handle values on the same line as section header (like "threads: 4,")
            value_part = section_match.group(2).strip()
            if value_part and not value_part.startswith('#'):  # Skip comments
                # Remove trailing comma and quotes
                value_part = _clean_value(value_part)
                if value_part:
                    # Special handling for threads value
                    if section_name == 'threads':
                        try:
                            current_rule['threads'] = int(value_part)
                        except ValueError:
                            # Try to evaluate if it's a simple expression
                            try:
                                current_rule['threads'] = int(eval(value_part))
                            except:
                                current_rule['threads'] = 1  # Default value
                    elif section_name == 'wrapper':
                        # Extract wrapper path (remove quotes and "master/" prefix)
                        wrapper_match = re.search(r'["\'](.+?)["\']', value_part)
                        if wrapper_match:
                            wrapper_path = wrapper_match.group(1)
                            # Remove "master/" prefix to get the actual wrapper name
                            if wrapper_path.startswith('master/'):
                                wrapper_path = wrapper_path[7:]  # Remove 'master/'
                            current_rule['wrapper'] = wrapper_path
                    elif section_name == 'conda':
                        conda_match = re.search(r'["\'](.+?)["\']', value_part)
                        if conda_match:
                            current_rule['conda'] = conda_match.group(1)
                    elif section_name == 'singularity':
                        singularity_match = re.search(r'["\'](.+?)["\']', value_part)
                        if singularity_match:
                            current_rule['singularity'] = singularity_match.group(1)
                    elif section_name == 'benchmark':
                        benchmark_match = re.search(r'["\'](.+?)["\']', value_part)
                        if benchmark_match:
                            current_rule['benchmark'] = benchmark_match.group(1)
                    elif section_name == 'shadow':
                        shadow_match = re.search(r'["\'](.+?)["\']', value_part)
                        if shadow_match:
                            current_rule['shadow'] = shadow_match.group(1)
                    else:
                        # For input, output, log, add to the appropriate section
                        _add_value_to_section(current_rule, section_name, value_part)
            continue
        
        # Process indented content within sections - handle all sections that were matched above
        if line.strip() and current_section and current_rule:
            # Check if it's an indented line (part of current section)
            if line.startswith(' ') or line.startswith('\t'):
                # Remove leading whitespace
                content = line.strip()
                
                # Skip empty lines and comments
                if not content or content.startswith('#'):
                    continue
                
                # Handle different section types - extended to handle more Snakemake directives
                if current_section == 'wrapper':
                    # Extract wrapper path (remove quotes and "master/" prefix)
                    wrapper_match = re.search(r'["\'](.+?)["\']', content)
                    if wrapper_match:
                        wrapper_path = wrapper_match.group(1)
                        # Remove "master/" prefix to get the actual wrapper name
                        if wrapper_path.startswith('master/'):
                            wrapper_path = wrapper_path[7:]  # Remove 'master/'
                        current_rule['wrapper'] = wrapper_path
                elif current_section == 'params' and '=' in content:
                    # Parse key=value format in params
                    parts = content.split('=', 1)
                    if len(parts) == 2:
                        key = parts[0].strip().strip('\'"')
                        value = parts[1].strip()
                        # Clean the value (remove trailing comma, quotes)
                        value = _clean_value(value)
                        # Try to convert value to appropriate type
                        try:
                            # Try to parse as YAML/JSON to get proper types
                            parsed_value = yaml.safe_load(value)
                            # Special handling for strings that look like lists in Snakefile format
                            if isinstance(parsed_value, str) and (parsed_value.startswith('[') and parsed_value.endswith(']')):
                                # Try to parse as list in Python format
                                try:
                                    parsed_value = eval(parsed_value)  # Safe for known values
                                except:
                                    pass  # Keep as string
                            value = parsed_value
                        except:
                            pass  # Keep as string if parsing fails
                        current_rule['params'][key] = value
                elif current_section in ['input', 'output', 'log']:
                    # Handle key=value format (like "bam="mapped/{sample}.bam"")
                    if '=' in content:
                        parts = content.split('=', 1)
                        if len(parts) == 2:
                            key = parts[0].strip().strip('\'"')
                            value = parts[1].strip()
                            # Clean the value (remove trailing comma, quotes)
                            value = _clean_value(value)
                            # Add as dict entry
                            if current_section == 'input':
                                if not isinstance(current_rule['input'], dict):
                                    current_rule['input'] = {}
                                current_rule['input'][key] = value
                            elif current_section == 'output':
                                if not isinstance(current_rule['output'], dict):
                                    current_rule['output'] = {}
                                current_rule['output'][key] = value
                            elif current_section == 'log':
                                if not isinstance(current_rule['log'], dict):
                                    current_rule['log'] = {}
                                current_rule['log'][key] = value
                    else:
                        # Simple value
                        value = content.strip()
                        # Clean the value (remove trailing comma, quotes)
                        value = _clean_value(value)
                        _add_value_to_section(current_rule, current_section, value)
                elif current_section == 'threads':
                    # Parse thread count - handle both standalone values and key=value format
                    content = content.strip().rstrip(',')
                    # Handle key=value format like "threads: 4" where it might appear as key=value inside the section
                    if '=' in content:
                        parts = content.split('=', 1)
                        if len(parts) == 2:
                            value = parts[1].strip()
                            value = _clean_value(value)
                        else:
                            value = content
                    else:
                        value = content
                    try:
                        current_rule['threads'] = int(value)
                    except ValueError:
                        # Try to evaluate if it's a simple expression
                        try:
                            current_rule['threads'] = int(eval(value))
                        except:
                            pass  # Keep as None if parsing fails
                elif current_section == 'conda':
                    # Parse conda environment
                    conda_match = re.search(r'["\'](.+?)["\']', content)
                    if conda_match:
                        current_rule['conda'] = conda_match.group(1)
                elif current_section == 'singularity':
                    # Parse singularity image
                    singularity_match = re.search(r'["\'](.+?)["\']', content)
                    if singularity_match:
                        current_rule['singularity'] = singularity_match.group(1)
                elif current_section == 'benchmark':
                    # Parse benchmark file
                    benchmark_match = re.search(r'["\'](.+?)["\']', content)
                    if benchmark_match:
                        current_rule['benchmark'] = benchmark_match.group(1)
                elif current_section == 'shadow':
                    # Parse shadow mode
                    shadow_match = re.search(r'["\'](.+?)["\']', content)
                    if shadow_match:
                        current_rule['shadow'] = shadow_match.group(1)
                elif current_section == 'resources':
                    # Parse key=value format in resources
                    if '=' in content:
                        parts = content.split('=', 1)
                        if len(parts) == 2:
                            key = parts[0].strip().strip('\'"')
                            value = parts[1].strip()
                            # Clean the value (remove trailing comma, quotes)
                            value = _clean_value(value)
                            # Try to convert value to appropriate type
                            try:
                                parsed_value = yaml.safe_load(value)
                                value = parsed_value
                            except:
                                pass  # Keep as string if parsing fails
                            if 'resources' not in current_rule:
                                current_rule['resources'] = {}
                            current_rule['resources'][key] = value
    
    # Don't forget to add the last rule
    if current_rule:
        rules.append(current_rule)
    
    return rules


def _clean_value(value: str) -> str:
    """Clean a value by removing trailing commas and extra quotes."""
    # Remove trailing comma and whitespace
    value = value.rstrip(',').strip()
    # Remove surrounding quotes (single or double)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    # Remove any remaining quotes
    value = value.strip('"').strip("'")
    return value


def _add_value_to_section(rule: Dict, section: str, value: str):
    """Helper to add a value to the appropriate section of a rule."""
    if section in ['input', 'output', 'log']:
        if isinstance(rule[section], list):
            rule[section].append(value)
        else:
            # If it's not a list but we want to add more values, convert to list
            if rule[section] is None:
                rule[section] = [value] if value else []
            elif isinstance(rule[section], str):
                rule[section] = [rule[section], value]
            elif isinstance(rule[section], list):
                rule[section].append(value)


def convert_rule_to_tool_process_call(rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert a parsed rule to a tool/process API call format.
    Only include fields that are supported by the API model.
    
    Args:
        rule: Dictionary representing a parsed rule with input, output, etc.
        
    Returns:
        Dictionary containing the tool/process call parameters, or None if invalid
    """
    if not rule.get('wrapper'):
        return None  # Need wrapper path
    
    # Convert to tool/process format with only supported API fields
    # These are the exact fields accepted by SnakemakeWrapperRequest
    tool_call = {
        "wrapper_name": rule['wrapper'],
        "inputs": rule.get('input', []) or [],
        "outputs": rule.get('output', []) or [],
        "params": rule.get('params', {}) or {},
        "threads": rule.get('threads', 1) or 1,
        "log": rule.get('log', []) or [],
        "extra_snakemake_args": "",
        "container": None,
        "benchmark": None,
        "resources": {},
        "shadow": None,
        "conda_env": None
    }
    
    return tool_call


def analyze_wrapper_test_directory(wrapper_path: str, snakefile_path: str) -> List[Dict[str, Any]]:
    """
    Analyze a wrapper test directory and convert all test rules to tool/process calls.
    
    Args:
        wrapper_path: Path to the wrapper directory
        snakefile_path: Path to the test Snakefile
        
    Returns:
        List of tool/process API calls that can be made based on the test Snakefile
    """
    # Read the Snakefile
    with open(snakefile_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse the rules
    rules = parse_snakefile_content(content)
    
    # Convert each rule to a tool/process call
    tool_calls = []
    for rule in rules:
        tool_call = convert_rule_to_tool_process_call(rule)
        if tool_call:
            # Add the rule name as a reference for identification
            tool_call['rule_name'] = rule['name']
            tool_calls.append(tool_call)
    
    return tool_calls


def generate_demo_calls_for_wrapper(wrapper_path: str) -> List[Dict[str, Any]]:
    """
    Generate demo tool/process calls for a wrapper by analyzing its test Snakefile.
    Returns the basic API call structure (just the payload for tool-processes).
    
    Args:
        wrapper_path: Path to the wrapper directory
        
    Returns:
        List of basic demo API call parameters (ready for tool-processes endpoint)
    """
    test_dir = Path(wrapper_path) / "test"
    snakefile = test_dir / "Snakefile"
    
    if not snakefile.exists():
        return []
    
    # Analyze the test Snakefile
    demo_calls = analyze_wrapper_test_directory(str(wrapper_path), str(snakefile))
    
    # Add example values and documentation to each call
    for call in demo_calls:
        # Add example documentation for user guidance
        call['example_info'] = {
            'rule_name': call.get('rule_name', 'unknown'),
            'description': f'Demo call for {call.get("wrapper_name", "unknown wrapper")}',
            'usage_notes': 'Replace placeholder values (like {sample}) with actual file paths'
        }
        
        # Create example file paths by replacing placeholders with actual values
        example_call = create_example_call(call)
        call['example_usage'] = example_call
        
    return demo_calls


def create_example_call(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an example API call with placeholder values replaced by example values.
    
    Args:
        tool_call: The parsed tool call with placeholders
        
    Returns:
        Dictionary with example values for demonstration
    """
    import copy
    example_call = copy.deepcopy(tool_call)
    
    # Replace placeholders in inputs and outputs with example values
    if isinstance(example_call['inputs'], list):
        example_call['inputs'] = [replace_placeholders(val, example_call.get('wrapper_name', 'wrapper')) for val in example_call['inputs']]
    elif isinstance(example_call['inputs'], dict):
        for key, val in example_call['inputs'].items():
            example_call['inputs'][key] = replace_placeholders(val, example_call.get('wrapper_name', 'wrapper'))
    
    if isinstance(example_call['outputs'], list):
        example_call['outputs'] = [replace_placeholders(val, example_call.get('wrapper_name', 'wrapper')) for val in example_call['outputs']]
    elif isinstance(example_call['outputs'], dict):
        for key, val in example_call['outputs'].items():
            example_call['outputs'][key] = replace_placeholders(val, example_call.get('wrapper_name', 'wrapper'))
    
    # Also update log if exists
    if isinstance(example_call['log'], list):
        example_call['log'] = [replace_placeholders(val, example_call.get('wrapper_name', 'wrapper')) for val in example_call['log']]
    elif isinstance(example_call['log'], dict):
        for key, val in example_call['log'].items():
            example_call['log'][key] = replace_placeholders(val, example_call.get('wrapper_name', 'wrapper'))
    
    return example_call


def replace_placeholders(text: str, wrapper_name: str) -> str:
    """
    Replace common placeholders in file paths with example values.
    
    Args:
        text: The text with placeholders
        wrapper_name: The wrapper name for context
        
    Returns:
        Text with placeholders replaced by example values
    """
    import re
    
    # Common placeholders to replace with examples
    examples = {
        r'\{sample\}': 'example_sample',
        r'\{tool\}': 'example_tool',
        r'\{name\}': 'example_name',
        r'\{group\}': 'example_group',
        r'\{unit\}': 'example_unit',
        r'\{batch\}': 'example_batch',
        # More generic
        r'\{.*?\}': 'example_value'  # Replace any remaining placeholders
    }
    
    result = text
    for pattern, replacement in examples.items():
        result = re.sub(pattern, replacement, result)
    
    return result


# Example usage:
if __name__ == "__main__":
    # Example: Analyze a specific test Snakefile
    test_snakefile = """
rule samtools_faidx:
    input:
        "{sample}.fa",
    output:
        "out/{sample}.fa.fai",
    log:
        "{sample}.log",
    params:
        extra="",
    wrapper:
        "master/bio/samtools/faidx"


rule samtools_faidx_bgzip:
    input:
        "{sample}.fa.bgz",
    output:
        fai="out/{sample}.fas.bgz.fai",
        gzi="out/{sample}.fas.bgz.gzi",
    log:
        "{sample}.bzgip.log",
    params:
        extra="",
    wrapper:
        "master/bio/samtools/faidx"
"""
    
    rules = parse_snakefile_content(test_snakefile)
    print(f"Found {len(rules)} rules:")
    
    for rule in rules:
        print(f"\nRule: {rule['name']}")
        print(f"  Wrapper: {rule['wrapper']}")
        print(f"  Input: {rule['input']}")
        print(f"  Output: {rule['output']}")
        print(f"  Params: {rule['params']}")
        print(f"  Log: {rule['log']}")
        print(f"  Threads: {rule['threads']}")
        
        # Convert to tool/process call
        tool_call = convert_rule_to_tool_process_call(rule)
        if tool_call:
            print(f"  Tool/Process Call: {tool_call['wrapper_name']}")
            print(f"  Inputs: {tool_call['inputs']}")
            print(f"  Outputs: {tool_call['outputs']}")
            print(f"  Params: {tool_call['params']}")