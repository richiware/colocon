# Requirements

* Must accept any `colcon`'s argument and pass it when calling `colcon`.
* `colocon` will be called from the project's root directory or the user will specify it using `--project-dir`.
`colocon` must obtain the project's name in that directory using the `colcon.pkg`, and its dependencies from
every dependency key that file supports: `dependencies`, `build-dependencies`, `run-dependencies` and
`test-dependencies`.
If that directory has no `colcon.pkg`, `colocon` must search the first level of its subdirectories for
packages, join the dependencies of every `colcon.pkg` found there, name the project after the directory holding
the worktree, and pass each package directory to `colcon`.
If no `colcon.pkg` is found either way, `colocon` must fall back on `CMakeLists.txt`, in the project directory
first and in the first level of its subdirectories otherwise, taking as dependencies the packages named by the
`find_package` commands of every listfile read, together with the `MODULE_FIND_PACKAGES` of any
`project_settings.cmake` beside it, which may be set by more than one command. Names `colocon` cannot resolve to a package, such as generator expressions,
must be passed over.
Then `colocon` must search the file `${project_name}.repos` and obtain the dependencies and versions.
* Must support a `dependency-locations` mapping in the configuration file, placing a dependency inside another
repository: the *repos* file must then be asked about that project instead of the dependency, and the directory
of its worktree holding the dependency is what must be passed to `colcon`. Without an explicit `path`, the
directory is the dependency's own name.
* Must offer a `-d`/`--diagnose` argument, before the verb, printing the packages of the project, its
dependencies and the directory each one resolved to, and then carrying on. Each dependency must also show where
it was first declared: the `colcon.pkg` file and the key declaring it, or the `CMakeLists.txt` file and the line
of the `find_package` command.
* Must leave the build and install directories to `colcon`. `colocon` must never add `--build-base` nor
`--install-base`, and must forward them untouched when the user passes them.
* Must default `--mixin` to `rel-with-deb-info` for the `build` verb, unless the user asks for a mixin.
* After calling `colcon`, `colocon` has to find all `compile_commands.json` and join them to a unique
`compile_commands.json`.
