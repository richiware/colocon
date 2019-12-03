# Requirements

* Must accept any `colcon`'s argument and pass it when calling `colcon`.
* `colocon` will be called from the project's root directory or the user will specify it using `--project-dir`.
`colocon` must obtain the project's name in that directory using the `colcon.pkg`.
Then `colocon` must search the file `${project_name}.repos` and obtain the dependencies and versions.
* Must detect cmake-build-type mixin. In case it is detected, `colocon` must change the `--build-base` to
`build-${cmake-build-type}`.
* If no `--install-base` passed, `colocon` must change `--install-base` to `${build-base}/install`.
* Must fill and pass to colcon correct `-fdebug-prefix-map` inside `-DCMAKE_CXX_FLAGS`.
* After calling `colcon`, `colocon` has to find all `compile_commands.json` and join them to a unique
`compile_commands.json`.

