# -----------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# -----------------------------------------------------------------------------

from __future__ import print_function

import json
import os
import re
from subprocess import CalledProcessError
import sys

from knack.prompting import prompt_y_n
from knack.util import CLIError

from azdev.utilities import (
    pip_cmd, display, heading, subheading, COMMAND_MODULE_PREFIX, EXTENSION_PREFIX,
    get_cli_repo_path, get_ext_repo_paths)


def _ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def _generate_files(env, generation_kwargs, file_list, dest_path):

    # allow sending a single item
    if not isinstance(file_list, list):
        file_list = [file_list]

    for metadata in file_list:
        # shortcut if source and dest filenames are the same
        if isinstance(metadata, str):
            metadata = {'name': metadata, 'template': metadata}

        with open(os.path.join(dest_path, metadata['name']), 'w') as f:
            f.write(env.get_template(metadata['template']).render(**generation_kwargs))


def create_module(mod_name='test', display_name=None, required_sdk=None,
                  sdk_client=None):
    repo_path = os.path.join(get_cli_repo_path(), 'src', 'command_modules')
    _create_package(COMMAND_MODULE_PREFIX, repo_path, False, mod_name, display_name, required_sdk, sdk_client)

def create_extension(ext_name='test', repo_name=None, display_name=None, required_sdk=None,
                     sdk_client=None):
    repo_paths = get_ext_repo_paths()
    repo_path = next((x for x in repo_paths if x.endswith('azure-cli-extensions')), None)
    if not repo_path:
        raise CLIError('Unable to find `azure-cli-extension` repo. Have you cloned it and added '
                       'with `azdev extension repo add`?')
    repo_path = os.path.join(repo_path, 'src')
    _create_package(EXTENSION_PREFIX, repo_path, True, ext_name, display_name, required_sdk, sdk_client)


def _create_package(prefix, repo_path, is_ext, name='test', display_name=None, required_sdk=None,
                    sdk_client=None):
    from jinja2 import Environment, PackageLoader

    if name.startswith(prefix):
        name = name[len(prefix):]

    heading('Create CLI {}: {}{}'.format('Extension' if is_ext else 'Module', prefix, name))

    # package_name is how the item should show up in `pip list`
    package_name = '{}{}'.format(prefix, name.replace('_', '-')) if not is_ext else name
    display_name = display_name or name.capitalize()

    kwargs = {
        'name': name,
        'mod_path': '{}{}'.format(prefix, name) if is_ext else 'azure.cli.command_modules.{}'.format(name),
        'display_name': display_name,
        'loader_name': '{}CommandsLoader'.format(display_name),
        'pkg_name': package_name,
        'ext_long_name': '{}{}'.format(prefix, name) if is_ext else None,
        'is_ext': is_ext
    }

    if required_sdk or sdk_client:
        version_regex = r'(?P<name>[a-zA-Z-]+)(?P<op>[~<>=]*)(?P<version>[\d.]*)'
        regex = re.compile(version_regex)
        version_comps = regex.match(required_sdk)
        sdk_kwargs = version_comps.groupdict()
        kwargs.update({
            'sdk_path': sdk_kwargs['name'].replace('-', '.'),
            'sdk_client': sdk_client,
            'dependencies': [sdk_kwargs]
        })

    new_package_path = os.path.join(repo_path, package_name)
    if os.path.isdir(new_package_path):
        if not prompt_y_n(
                "{} '{}' already exists. Overwrite?".format('Extension' if is_ext else 'Module', package_name),
                default='n'):
            return

    ext_folder = '{}{}'.format(prefix, name) if is_ext else None

    # create folder tree
    if is_ext:
        _ensure_dir(os.path.join(new_package_path, ext_folder, 'tests', 'latest'))
        _ensure_dir(os.path.join(new_package_path, ext_folder, 'vendored_sdks'))
    else:
        _ensure_dir(os.path.join(new_package_path, 'azure', 'cli', 'command_modules', name, 'tests', 'latest'))
    env = Environment(loader=PackageLoader('azdev', 'mod_templates'))

    # generate code for root level
    dest_path = new_package_path
    root_files = [
        'HISTORY.rst',
        'MANIFEST.in',
        'README.rst',
        'setup.cfg',
        'setup.py'
    ]
    if not is_ext:
        root_files.append('azure_bdist_wheel.py')
    _generate_files(env, kwargs, root_files, dest_path)

    if not is_ext:
        dest_path = os.path.join(dest_path, 'azure')
        pkg_init = {'name': '__init__.py', 'template': 'pkg_declare__init__.py'}
        _generate_files(env, kwargs, pkg_init, dest_path)

        dest_path = os.path.join(dest_path, 'cli')
        _generate_files(env, kwargs, pkg_init, dest_path)

        dest_path = os.path.join(dest_path, 'command_modules')
        _generate_files(env, kwargs, pkg_init, dest_path)

    dest_path = os.path.join(dest_path, ext_folder if is_ext else name)
    module_files = [
        {'name': '__init__.py', 'template': 'module__init__.py'},
        '_client_factory.py',
        '_help.py',
        '_params.py',
        '_validators.py',
        'commands.py',
        'custom.py'
    ]
    if is_ext:
        module_files.append('azext_metadata.json')
    _generate_files(env, kwargs, module_files, dest_path)

    dest_path = os.path.join(dest_path, 'tests')
    blank_init = {'name': '__init__.py', 'template': 'blank__init__.py'}
    _generate_files(env, kwargs, blank_init, dest_path)

    dest_path = os.path.join(dest_path, 'latest')
    test_files = [
        blank_init,
        {'name': 'test_{}_scenario.py'.format(name), 'template': 'test_service_scenario.py'}
    ]
    _generate_files(env, kwargs, test_files, dest_path)

    if not is_ext:
        # install the newly created module
        try:
            pip_cmd("install -q -e {}".format(new_package_path), "Installing `{}{}`...".format(prefix, name))
        except CalledProcessError as err:
            # exit code is not zero
            raise CLIError("Failed to install. Error message: {}".format(err.output))
        finally:
            # Ensure that the site package's azure/__init__.py has the old style namespace
            # package declaration by installing the old namespace package
            pip_cmd("install -q -I azure-nspkg==1.0.0", "Installing `azure-nspkg`...")
            pip_cmd("install -q -I azure-mgmt-nspkg==1.0.0", "Installing `azure-mgmt-nspkg`...")
    else:
        # TODO: Install extension
        result = pip_cmd('install -e {}'.format(new_package_path), "Installing `{}{}`...".format(prefix, name))
        if result.error:
            raise result.error  # pylint: disable=raising-bad-type


    if not is_ext:
        # TODO: add module to the azure-cli's "setup.py" file
        # TODO: add module to doc source map
        pass

    # TODO: add module to Github code owners file

    display('\nCreation of {prefix}{mod} successful! Run `az {mod} -h` to get started!'.format(prefix=prefix, mod=name))


def _make_snake_case(s):
    snake_regex_1 = re.compile('(.)([A-Z][a-z]+)')
    snake_regex_2 = re.compile('([a-z0-9])([A-Z])')
    if isinstance(s, str):
        s1 = re.sub(snake_regex_1, r'\1_\2', s)
        return re.sub(snake_regex_2, r'\1_\2', s1).lower()
    return s


def show_command_tree(cmd, file):

    json_data = None
    try:
        with open(file, 'r') as f:
            json_data = json.loads(f.read())
    except (OSError, IOError):
        pass

    if not json_data:
        raise CLIError('unable to load JSON file: {}'.format(file))

    models = json_data['models']
    operations = json_data['operations']

    subheading('Operations')

    prefix_dict = {
        'create': ['create', 'create_or_update'],
        'update': ['update', 'patch'],
        'list': ['list', 'list_by', 'list_all'],
        'delete': ['delete'],
        'show': ['get'],
        'other': ['check', 'regenerate']
    }

    # build up reverse prefix dictionary
    reverse_prefix_dict = {}
    for key, values in prefix_dict.items():
        for val in values:
            reverse_prefix_dict[val] = key
    sorted_prefixes = sorted(reverse_prefix_dict.keys(), key=len, reverse=True)

    command_tree = {
        'name': 'ROOT',
        'subgroups': [],
        'commands': []
    }

    client_objects = []

    for client, data in operations.items():
        snake_client = _make_snake_case(client)
        client_comps = snake_client.split('_')
        try:
            client_comps.remove('operations')
        except ValueError:
            pass
        client_object = '_'.join(client_comps) or 'operations'
        client_objects.append(client_object)

        sub_group_node = {
            'name': client_object,
            'subgroups': [],
            'commands': []
        }
        for func_data in data['functions'].values():
            func_name = func_data['name']
            print(func_name)
        #     for prefix in sorted_prefixes:
        #         if func_name.startswith(prefix):
        #             command_name = None
        #             command_type = reverse_prefix_dict[prefix]
        #             if command_type == 'other':
        #                 command_name = func_name
        #             else:
        #                 remainder = func_name[len(prefix):]
        #                 if remainder.startswith('_'):
        #                     remainder = remainder[1:]
        #                 command_name = command_type
        #                 if remainder:
        #                     # TODO: subgroups
        #                     print("OMG WHAT IS {}".format(remainder))
        #                     continue
        #             sub_group_node['commands'].append({
        #                 'name': command_name
        #             })
        #             break
        # command_tree['subgroups'].append(sub_group_node)
    print(client_objects)