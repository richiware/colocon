# colocon

This utility configures and uses `colcon` in a different manner.
The default way of working with `colcon` is having all repositories cloned under a directory with an specific version.
This way is not proper if you like to work with Git worktrees as I like.
Therefore, I created this utility to make `colcon` works in another way.

`colocon` is prepare to work in the following development environment:

* Repositories are located in one or several directories:
```
repos
|
|__fastcdr
|
|__foonathan_memory_vendor
|
|__fastrtps
```
* Inside each project there are several directories.
Each one is a Git worktree of the repository. Usually at least one should be: `master`.
```
repos
|
|__fastcdr
|  |
|  |__master
|  |
|  |__v1.0.11
|
|__foonathan_memory_vendor
|  |
|  |__master
|
|__fastrtps
   |
   |__master
   |
   |__1.9.x
```


## Default configuration

`colocon` uses the default configuration file `~/.colcon/colocon.yaml` to set default options.

```yaml
{
    "search-paths" : [ "/home/developer/repos" ],
    "compile_commands" : True
}
```

* `search-paths`: list of paths where `colocon` will search the dependencies.
* `compile_commands`: if True, after calling `colcon`, `colocon` will search all `compile_commands.json` and join them
in one `compile_commands.json` in the working directory.

## What `colocon` does?

`colocon` searches in the working directory or in the path passed with the argument `--project-dir` a `colcon.pkg`
file. This file is used to get the project to be compiled and the dependencies. Afterwards `colocon` searches a *repos*
file using the project's name (`{project's name}.repos`) and also gets the listed dependencies and their versions. Makes
an *inner-join* between dependencies information of `colcon.pkg` and `{project_name}.repos`. `colocon` will look for the
resulted dependencies (and the worktree correspondent to the version) in the `search-paths`. At the end `colocon` will
call `colcon` to build the project and all the found dependencies.
