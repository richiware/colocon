# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

options = []
search_paths = []
compile_commands = False


def arg_parser(args):
    global options
    parser = argparse.ArgumentParser(
            prog='colocon',
            description='Helper to run colcon in different way.')
    parser.add_argument(
            '-p', '--project-dir', default='.',
            help='Root directory of the main project, where its CMakeList.txt will be found.')
    parser.add_argument(
            '-a', '--all', action='store_true',
            help='Instead of inner-join between dependencies of "colcon.pkg" and "{project_name}.repos",\
             a left-join will be done and use all dependencies')
    parser.add_argument('rest', nargs=argparse.REMAINDER)
    options = vars(parser.parse_args(args))


def load_defaults():
    global search_paths
    global compile_commands
    defaults_path = Path.home() / '.colcon/colocon.yaml'
    if not defaults_path.is_file():
        return

    defaults_content = defaults_path.read_text()
    yaml_content = yaml.safe_load(defaults_content)
    if 'search-paths' in yaml_content:
        search_paths = yaml_content['search-paths']
    if 'compile_commands' in yaml_content:
        compile_commands = yaml_content['compile_commands']


def get_project_info():
    global options

    # Use colcon.pkg to get information
    colcon_pkg_path = Path(options['project_dir']) / 'colcon.pkg'
    if not colcon_pkg_path.is_file():
        return None, None
    colcon_pkg_content = colcon_pkg_path.read_text()
    yaml_content = yaml.safe_load(colcon_pkg_content)

    if 'name' not in yaml_content:
        return None, None

    return yaml_content['name'], yaml_content['dependencies'] if 'dependencies' in yaml_content else None


def get_colcon_paths(project_name, dependencies):
    global options
    global search_paths
    final_dependencies = {}
    yaml_content = None

    # Use {project_name}.repos to get info about dependencies
    repos_path = Path(options['project_dir']) / (project_name + '.repos')
    if repos_path.is_file():
        repos_content = repos_path.read_text()
        yaml_content = yaml.safe_load(repos_content)

        for repository in yaml_content['repositories']:
            found = False
            for dependency in dependencies:
                if repository == dependency:
                    found = True
            if not found and options['all'] and not repository == project_name:
                found = True
            if found:
                if 'version' in yaml_content['repositories'][repository]:
                    final_dependencies[repository] = yaml_content['repositories'][repository]['version']
                else:
                    final_dependencies[repository] = 'master'

    colcon_paths = []
    colcon_rec_paths = []
    meta_paths = {}
    for dep in final_dependencies:
        found = False
        for search_path in search_paths:
            colcon_path_base = Path(search_path) / dep
            if colcon_path_base.is_dir():
                colcon_path = colcon_path_base / final_dependencies[dep]
                if colcon_path.is_dir():
                    if 'recursive' in yaml_content['repositories'][dep] and yaml_content['repositories'][dep]['recursive']:
                        colcon_rec_paths += [str(colcon_path)]
                    else:
                        colcon_paths += [str(colcon_path)]
                    meta_paths[dep] = str(colcon_path)
                    found = True
                    break
                else:
                    colcon_path = colcon_path_base / 'master'
                    if colcon_path.is_dir():
                        if 'recursive' in yaml_content['repositories'][dep] and yaml_content['repositories'][dep]['recursive']:
                            colcon_rec_paths += [str(colcon_path)]
                        else:
                            colcon_paths += [str(colcon_path)]
                        meta_paths[dep] = str(colcon_path)
                        found = True
                        break
        if not found:
            print('Cannot find path for ' + dep)

    if not '.' == options['project_dir']:
        project_path = Path(options['project_dir'])
        colcon_paths += [str(project_path.resolve())]
        meta_paths[project_name] = str(project_path.resolve())
    else:
        current_path = Path('.')
        colcon_paths += [str(current_path.resolve())]
        meta_paths[project_name] = str(current_path.resolve())

    return colcon_paths, colcon_rec_paths, meta_paths


def generate_colcon_meta(build_dir, meta_paths):
    yaml_content = None
    colcon_meta_path = Path('colcon.meta')
    if colcon_meta_path.is_file():
        colcon_meta_content = colcon_meta_path.read_text()
        yaml_content = yaml.safe_load(colcon_meta_content)

    if not yaml_content:
        yaml_content = {'names': {}}

    for lib in meta_paths:
        if lib not in yaml_content['names']:
            yaml_content['names'][lib] = {}
        if 'cmake-args' not in yaml_content['names'][lib]:
            yaml_content['names'][lib]['cmake-args'] = []
        yaml_content['names'][lib]['cmake-args'] += ["-DCMAKE_CXX_FLAGS=-ffile-prefix-map=" + meta_paths[lib] + "=.",
                                                    "-DCMAKE_C_FLAGS=-ffile-prefix-map=" + meta_paths[lib] + "=."]

        if not os.path.exists(build_dir):
            os.makedirs(build_dir)
        with open(build_dir + '/colcon.meta', 'w') as file:
            document = yaml.dump(yaml_content, file)


def support_paths(verb):
    if verb == 'build' or verb == 'test' or verb == 'graph':
        return True
    return False


def execute_colcon(colcon_paths, colcon_rec_paths, meta_paths):
    colcon_args = ['colcon']
    build_suffix = 'rel-with-deb-info'

    if len(options['rest']) == 0:
        return False, None

    verb = options['rest'][0]
    colcon_args += [verb]

    if support_paths(verb) and colcon_paths:
        colcon_args += ['--paths'] + colcon_paths

    if support_paths(verb) and colcon_rec_paths:
        colcon_args += ['--base-paths'] + colcon_rec_paths
    if 'build' == verb:
        if '--mixin' in options['rest']:
            position = options['rest'].index('--mixin')
            del options['rest'][position]
            build_suffix = options['rest'][position]
            colcon_args += ['--mixin', options['rest'][position]]
            del options['rest'][position]
        else:
            colcon_args += ['--mixin', 'rel-with-deb-info']

    build_dir = 'build'
    if '--build-base' not in options['rest']:
        if sys.platform != 'win32':
            build_dir += '-' + build_suffix
            colcon_args += ['--build-base', build_dir]
    else:
        position = options['rest'].index('--build-base')
        build_dir = options['rest'][position + 1]

    if '--install-base' not in options['rest'] and verb != 'graph':
        colcon_args += ['--install-base', build_dir + '/install']

    # generate_colcon_meta(build_dir, meta_paths)
    # colcon_args += ['--meta', build_dir]

    colcon_args += options['rest'][1:]

    try:
        retcode = subprocess.call(colcon_args)
    except KeyboardInterrupt:
        retcode = -1

    if retcode == 0:
        return True, build_dir

    return False, None


def generate_compile_commands(build_dir):
    # Generate the compile_commands.json
    find_proc = subprocess.Popen(
            'find ' + build_dir + ' -iname compile_commands.json -print0 | grep -z . | xargs -0',
            stdout=subprocess.PIPE, shell=True)
    find_proc.wait()
    list_files = find_proc.stdout.readline().decode('utf-8').rstrip()
    find_proc.communicate()
    retcode = find_proc.returncode

    if retcode == 0:
        subprocess.call('jq -s add ' + list_files + ' > compile_commands.json', shell=True)


def main(argv=None):
    """
    Starting point of the command

    Logic:

    * Get arguments
    * Get default values from configuration
    --- * Find the CMakeLists.txt file and detect the CMake's project.
    * Read colcon.pkg and get project
    * Read {project_name}.repos and get dependencies versions
    * Generate colcon paths to pass using '--paths'
    * Get default cmake-args and add '-ffile-prefix-map'
    * Prepare arguments and call colcon

    :param list argv: The list of arguments
    :returns: The return code
    """

    arg_parser(args=argv)

    load_defaults()

    project_name, depends = get_project_info()

    if project_name is None:
        print("Cannot get info from colcon.pkg")
        return -1

    colcon_paths, colcon_rec_paths, meta_paths = get_colcon_paths(project_name, depends)

    retcode, build_dir = execute_colcon(colcon_paths, colcon_rec_paths, meta_paths)
    if not retcode:
        return -1

    if compile_commands:
        generate_compile_commands(build_dir)

    return 0
