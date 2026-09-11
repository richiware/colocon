# colocon

[![CI](https://github.com/richiware/colocon/actions/workflows/ci.yml/badge.svg)](https://github.com/richiware/colocon/actions/workflows/ci.yml)

A thin wrapper around [`colcon`](https://colcon.readthedocs.io) for projects kept in **git worktrees**.

`colcon` expects a single workspace holding every repository at one version. That model gets in the way as soon
as you keep several branches of the same repository side by side — which is exactly what git worktrees are for.
`colocon` bridges the two: it works out which worktree each dependency should be built from, hands the resulting
paths to `colcon`, and leaves every other decision to `colcon` itself.

- [Repository layout](#repository-layout)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Describing a project](#describing-a-project)
- [Projects of several packages](#projects-of-several-packages)
- [Projects without a `colcon.pkg`](#projects-without-a-colconpkg)
- [Which description wins](#which-description-wins)
- [How dependencies are resolved](#how-dependencies-are-resolved)
- [Compilation database](#compilation-database)
- [Development](#development)

## Repository layout

`colocon` expects one directory per repository, and inside it one directory per worktree, named after the branch
or tag it holds:

```
~/repos/                     <- a search path
├── nebula/
│   ├── master
│   └── feature/warp-drive
├── quasar/
│   ├── master
│   └── 2.3.x
├── pulsar/
│   └── master
└── stardust/
    └── 1.0
```

Create such a worktree the usual way:

```bash
git -C ~/repos/quasar/master worktree add ../2.3.x 2.3.x
```

You may keep repositories under more than one search path; they are searched in the order they are configured.

## Installation

Requires Python 3.10+ and `colcon` on `PATH`.

```bash
pipx install git+https://github.com/richiware/colocon.git
```

## Configuration

`colocon` reads `~/.colcon/colocon.yaml`:

```yaml
search-paths:
  - ~/repos
  - /opt/vendor/repos
compile_commands: true
```

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `search-paths` | list of paths | empty | Where to look for dependency repositories, in order. |
| `compile_commands` | boolean | `false` | Join every `compile_commands.json` after a successful build. |

A search path may start with `~`, which is expanded to your home directory. Environment variables are **not**
expanded, so a path such as `$HOME/repos` silently matches nothing — write `~/repos` instead. A missing or empty
configuration file is fine: `colocon` then reports every dependency it could not locate and builds the project
on its own.

## Usage

Run `colocon` from a worktree, with any `colcon` verb and arguments:

```bash
cd ~/repos/nebula/feature/warp-drive
colocon build
colocon build --mixin debug --packages-select nebula
colocon test
```

### Options

`colocon` owns a single argument; everything else is forwarded to `colcon` untouched.

| Option | Meaning |
| --- | --- |
| `-p`, `--project-dir DIR` | Root of the project to build. Defaults to the working directory. |

It must come **before** the verb: everything from the verb onwards belongs to `colcon`.

### What `colocon` adds

For the `build`, `test` and `graph` verbs:

| Argument | Value |
| --- | --- |
| `--paths` | The worktree of each resolved dependency, and the project directory itself last. |
| `--base-paths` | The worktree of each dependency marked `recursive`. |

For `build` only, `--mixin rel-with-deb-info` is added unless you pass a `--mixin` of your own.

Nothing else is touched. In particular `colocon` **never** chooses where `colcon` builds or installs: it adds
neither `--build-base` nor `--install-base`, and forwards both untouched when you pass them.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | `colcon.pkg` could not be read, or no verb was given. |
| `2` | An argument was rejected: unknown to `colocon`, or a `--build-base` with no value. |
| `130` | Interrupted with <kbd>Ctrl</kbd>+<kbd>C</kbd>. |
| *other* | Whatever `colcon` returned, forwarded unchanged. |

## Describing a project

The files in the project's worktree drive the resolution.

### `colcon.pkg`

The project's own name and the dependencies it wants built alongside it:

```yaml
name: nebula
dependencies:
  - quasar
build-dependencies:
  - stardust
```

`colocon` reads the project's `name` and every dependency key that
[`colcon.pkg`](https://colcon.readthedocs.io/en/released/user/configuration.html#colcon-pkg-files) defines:

| Key | Meaning |
| --- | --- |
| `dependencies` | Needed for every phase. |
| `build-dependencies` | Needed to build. |
| `run-dependencies` | Needed to run. |
| `test-dependencies` | Needed to test. |

Whichever phase asks for a dependency, its worktree has to be in the workspace, so `colocon` takes the union of
all four keys — a package named by several of them is passed once. Every other key, such as `type` or `hooks`,
belongs to `colcon` and is left untouched.

### `<project>.repos`

A [vcstool](https://github.com/dirk-thomas/vcstool) *repos* file named after the project — `nebula.repos` — saying
which version of each repository this project expects:

```yaml
repositories:
  quasar:
    type: git
    url: git@github.com:example/quasar.git
    version: 2.3.x
  pulsar:
    type: git
    url: git@github.com:example/pulsar.git
    version: master
  stardust:
    type: git
    url: git@github.com:example/stardust.git
    version: "1.0"
    recursive: true
```

| Key | Meaning |
| --- | --- |
| `version` | Worktree to build this dependency from. Defaults to `master`. |
| `recursive` | `colocon` extension. Pass this repository through `--base-paths`, so `colcon` searches it recursively for packages. Useful for a repository holding several packages. |

> **Quote numeric versions.** YAML resolves an unquoted `1.10` to the number `1.1`, and the worktree is then
> looked up under the wrong name. Write `version: "1.10"`.

### Projects of several packages

A repository often holds more than one package, with no package at its root. When the project directory has no
`colcon.pkg`, `colocon` looks one level down for directories that do, and treats them as the project:

```
~/repos/nebula/main/
├── nebula.repos
├── core/
│   └── colcon.pkg      name: nebula_core,  dependencies: [quasar]
├── tools/
│   └── colcon.pkg      name: nebula_tools, test-dependencies: [pulsar]
└── docs/               no colcon.pkg, ignored
```

The dependencies of every package found are joined, and each package directory is passed to `colcon` — `--paths`
does not recurse, so a single path to the project directory would find nothing:

```console
$ colocon build
colcon build --paths ~/repos/quasar/2.3.x ~/repos/pulsar/master \
             ~/repos/nebula/main/core ~/repos/nebula/main/tools --mixin rel-with-deb-info
```

**Only the first level is searched.** A package nested deeper is not found, since `colcon` crawls further on
its own once it is pointed at a package directory.

A `colcon.pkg` in the project directory always wins: the subdirectories are searched only in its absence.

### Projects without a `colcon.pkg`

A project that never adopted `colcon.pkg` is described by its CMake listfiles instead. When no `colcon.pkg` is
found — neither in the project directory nor one level down — `colocon` reads `CMakeLists.txt`, and every
package named by a `find_package` command counts as a dependency:

```cmake
cmake_minimum_required(VERSION 3.16)
project(nebula VERSION 1.0 LANGUAGES CXX)

find_package(quasar 2.3 REQUIRED)       # a dependency
find_package(Threads REQUIRED)          # not in nebula.repos, so ignored
# find_package(pulsar REQUIRED)         # commented out, so not read
```

```console
$ colocon build
colcon build --paths ~/repos/quasar/2.3.x ~/repos/nebula/main --mixin rel-with-deb-info
```

As with `colcon.pkg`, a `CMakeLists.txt` in the project directory describes a single package, and otherwise the
first level of subdirectories is searched, each one found becoming a package of the project.

The commands are read, not evaluated, which is worth keeping in mind:

- A `find_package` naming nothing in the *repos* file — `Threads`, `OpenSSL`, and the like — is dropped by the
  join without a word, so listfiles need no cleaning up.
- Conditions are not evaluated: a `find_package` inside an `if` block counts, whichever way the condition would
  have gone.
- A name built from a variable, `find_package(${DEPENDENCY})`, is skipped, since there is no telling what it
  would expand to.
- Commented-out commands, in either `#` or `#[[ ]]` form, are not read.

### Which description wins

Four places are tried, and the first holding a package describes the project:

| | Place | Dependencies from |
| --- | --- | --- |
| 1 | `colcon.pkg` in the project directory | its dependency keys |
| 2 | `colcon.pkg` one level down | the dependency keys of each |
| 3 | `CMakeLists.txt` in the project directory | its `find_package` commands |
| 4 | `CMakeLists.txt` one level down | the `find_package` commands of each |

Only the first match is used: a single `colcon.pkg` in one subdirectory describes the project on its own, and a
sibling offering only a `CMakeLists.txt` is not picked up. Add a `colcon.pkg` to a package to state its
dependencies exactly, and none of its listfiles are read.

Except in the first case, no file states a project name, so `colocon` takes it from the directory holding the
worktree — under `~/repos/nebula/main` it reads `nebula.repos`.

## How dependencies are resolved

1. Find the project's packages and their dependencies, from `colcon.pkg` or from `CMakeLists.txt` — see
   [Which description wins](#which-description-wins).
2. Read the `repositories` of `<name>.repos`.
3. Join the two: a repository is selected when the project declares it as a dependency, so a *repos* file may
   pin versions for more repositories than a given project needs.
4. For each selected repository, look for the first of these that exists, across the search paths in order:
   `<search-path>/<name>/<version>`, then `<search-path>/<name>/master`.
5. Pass what was found to `colcon`, together with the project's own package directories.

A dependency whose worktree cannot be found is reported on stderr and skipped — the build still runs, and
`colcon` fails later if the dependency was really needed.

### Chains of dependencies

`colocon` reads the `colcon.pkg` of the project it was run from, and of no other. It does not walk the
dependency graph — that is `colcon`'s job.

The files above describe such a chain: `nebula` depends on `quasar`, and `quasar` in turn depends on `pulsar`.
Because `nebula`'s `colcon.pkg` declares only `quasar` and `stardust`, `pulsar` gets no path even though the
*repos* file pins a version for it:

```console
$ colocon build
colcon build --paths ~/repos/quasar/2.3.x ~/repos/nebula/master \
             --base-paths ~/repos/stardust/1.0 --mixin rel-with-deb-info
```

To cover the whole chain, declare every level in `colcon.pkg`. The phase keys keep that readable, since a level
needed only to build or only to test can be declared as such:

```yaml
name: nebula
dependencies:
  - quasar
  - pulsar
build-dependencies:
  - stardust
```

```console
$ colocon build
colcon build --paths ~/repos/quasar/2.3.x ~/repos/pulsar/master ~/repos/nebula/master \
             --base-paths ~/repos/stardust/1.0 --mixin rel-with-deb-info
```

## Compilation database

With `compile_commands: true`, a successful build is followed by a merge of every `compile_commands.json` found
under the build directory into a single one in the working directory, which is what most language servers expect.

The build directory searched is `colcon`'s own default, `build`, or the one you passed with `--build-base`. The
merge is pure Python — no `find`, `xargs` or `jq` needed — and a database that cannot be read is reported without
failing the build.

## Development

```bash
git clone git@github.com:richiware/colocon.git
cd colocon
pip install -e ".[dev]"
pre-commit install     # optional: runs the linter on every commit
```

| Command | Purpose |
| --- | --- |
| `pytest` | Run the test suite. |
| `ruff check .` | Lint. |
| `mypy` | Type check. |

Install the package as editable before running the tests: the sources live in `src/`, so a non-editable install
would leave `pytest` testing the installed copy instead of your working tree.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
