#!/usr/bin/env python3

import json

from typing import Dict, List, Tuple

import click
import tabulate
import yaml

_UNCONVERTED_SUFFIXES = ["Ref", "Condition"]
_FN_PREFIX = "Fn::"


class CfnYamlLoader(yaml.SafeLoader):
    """
    Loader for CloudFormation templates written in YAML.
    """

    pass


def _multi_constructor(loader, tag_suffix, node):
    if tag_suffix not in _UNCONVERTED_SUFFIXES:
        tag_suffix = f"{_FN_PREFIX}{tag_suffix}"

    constructors = {
        yaml.ScalarNode: loader.construct_scalar,
        yaml.SequenceNode: loader.construct_sequence,
        yaml.MappingNode: loader.construct_mapping,
    }

    constructor = None

    if tag_suffix == "Fn::GetAtt":
        constructor = _construct_getatt
    for node_type, type_constructor in constructors.items():
        if isinstance(node, node_type):
            constructor = type_constructor

    if not constructor:
        raise TypeError(f"Unsupported node: {type(node)}")

    return {tag_suffix: constructor(node)}


def _construct_getatt(node):
    if isinstance(node.value, str):
        resource, _, attribute = node.value.partition('.')
        return [resource, attribute]
    if isinstance(node.value, list):
        return [s.value for s in node.value]
    raise TypeError(f"Unexpected node type: {type(node.value)}")


CfnYamlLoader.add_multi_constructor("!", _multi_constructor)


def parse_template(template_file):
    return yaml.load(template_file, CfnYamlLoader)


def parse_parameters(parameter_data: Dict[str, Dict[str, str]], defaults=False) -> List[Tuple[str, str, str, str]]:
    formatted_parameters = []
    for name, data in parameter_data.items():
        fields = (name, data.get('Type', 'String'), data.get('Description', ''), data.get('Default', ''))
        if defaults or not data.get('Default'):
            formatted_parameters.append(fields)
    return formatted_parameters


def create_table(parameter_data):
    table_headers = ('Name', 'Type', 'Description', 'Default')
    table = tabulate.tabulate(parameter_data, headers=table_headers, tablefmt="psql")
    return table


def create_json(parameter_data):
    data = []
    for name, _type, _description, default in parameter_data:
        data.append({'ParameterKey': name, 'ParameterValue': default})
    return json.dumps(data, indent=4)

@click.command(name="cfn-params")
@click.option(
    '--format',
    type=click.Choice(['table', 'json']),
    default='table',
    help="The output format to use"
)
@click.argument(
    'template-file',
    type=click.File(),
)
def main(template_file, format):
    """
    Print all the Parameters of a CloudFormation template, either in a table
    or JSON format.

    The Table format prints the parameter name, description, type, and default.
    The JSON format output is the same as the expected schema for providing
    parameter values to a CreateStack (or similar) command; the default (if there
    is one) will be used to pre-populate the ParameterValue field. 
    """
    template = parse_template(template_file)
    params = template.get('Parameters', [])
    parsed = parse_parameters(params)
    if format == "table":
        output = create_table(parsed)
    elif format == "json":
        output = create_json(parsed)
    click.echo(output)


if __name__ == '__main__':
    main()