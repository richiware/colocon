# Requirements

* Must accept any `colcon`'s argument and pass it when calling `colcon`.
* `colocon` will be called from the project's root directory or the user will specify it using `--project-dir`.
`colocon` must obtain the project's name in that directory using the `colcon.pkg`.
Then `colocon` must search the file `${project_name}.repos` and obtain the dependencies and versions.
* Must leave the build and install directories to `colcon`. `colocon` must never add `--build-base` nor
`--install-base`, and must forward them untouched when the user passes them.
* Must default `--mixin` to `rel-with-deb-info` for the `build` verb, unless the user asks for a mixin.
* Must fill and pass to colcon correct `-fdebug-prefix-map` inside `-DCMAKE_CXX_FLAGS`.
* After calling `colcon`, `colocon` has to find all `compile_commands.json` and join them to a unique
`compile_commands.json`.
