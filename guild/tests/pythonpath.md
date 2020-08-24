# Python Path

These tests illustrate how Guild configures the Python system path
under various scenarios.

We use the `pythonpath` sample project.

    >>> project = Project(sample("projects", "pythonpath"))

Here's a helper function that returns the Python system path from the
project `sys_path_test.py` script.

    >>> def sys_path_for_op(op, **kw):
    ...     import json
    ...     run, out = project.run_capture(op, **kw)
    ...     return run, json.loads(out)

Helper functions to assert that a Python path is a run directory.

    >>> def assert_run_dir(path, run):
    ...     assert path == "" or path == run.dir, (path, run.dir)

## Run script directly

Guild copies operation source code to the run directory and inserts
the source code destination into the Python system path as the first
non-empty value. Subsequent path entries are those generated by the
Python runtime.

    >>> run, sys_path = sys_path_for_op("sys_path_test.py")

    >>> sys_path[0] in ("", run.dir), (sys_path[0], run.dir)
    (True, ...)

    >>> sys_path[1]
    '.../.guild/sourcecode'

Confirm that the second path entry is the run directory source code
path.

    >>> sys_path[1] == run.guild_path("sourcecode"), sys_path[1], run.dir
    (True, ...)

Confirm that the project directory is not in the path.

    >>> project.cwd not in sys_path, project.cwd, sys_path
    (True, ...)

## Default operation

The `default` op runs the `test` module without additional
configuration. The behavior is the same as when running `sys_path_test.py`
diretly (above).

    >>> run, sys_path = sys_path_for_op("default")

    >>> sys_path[0] in ("", run.dir), (sys_path[0], run.dir)
    (True, ...)

    >>> sys_path[1]
    '.../.guild/sourcecode'

    >>> sys_path[1] == run.guild_path("sourcecode"), sys_path[1], run.dir
    (True, ...)

    >>> project.cwd not in sys_path, project.cwd, sys_path
    (True, ...)

## Alternative source code destination

The `sourcecode-dest` operation configures the destination path for
source code. Guild uses this to copy operation source code to an
alternative location under the run directory. In this case, the
operation configures the target as `src`.

    >>> run, sys_path = sys_path_for_op("sourcecode-dest")

    >>> sys_path[0] in ("", run.dir), (sys_path[0], run.dir)
    (True, ...)

    >>> sys_path[1]
    '.../src'

In this case, the default location for run source code --
`.guild/sourcecode` -- is not in the path.

    >>> run.guild_path("sourcecode") not in sys_path, run.dir, sys_path
    (True, ...)

Neither is the project directory.

    >>> project.cwd not in sys_path, project.cwd, sys_path
    (True, ...)

Instead, the configured source code destination --- `src` -- is in the
path at the top non-empty location:

    >>> sys_path[1] == path(run.dir, "src"), sys_path[1], run.dir
    (True, ...)

## Use of PYTHONPATH env

We can specify `PYTHONPATH` to include additional path *after* the run
source code directory and Guild program paths.

We can use `PYTHONPATH` to include the project directory.

    >>> run, sys_path = sys_path_for_op(
    ...     "sys_path_test.py",
    ...     extra_env={"PYTHONPATH": project.cwd})

    >>> sys_path[0] in ("", run.dir), (sys_path[0], run.dir)
    (True, ...)

    >>> sys_path[1]
    '.../.guild/sourcecode'

Note that the run source code location is still the first non-blank path.

    >>> sys_path[1] == run.guild_path("sourcecode"), sys_path[1], run.dir
    (True, ...)

In this case, however, the project directory *is* included in the path.

    >>> project.cwd in sys_path, project.cwd, sys_path
    (True, ...)

## Use of operation env

An operation can define `PYTHONPATH` in `env` to specify entries that
are included *before* any other Python path locations. The
`pythonpath-env` operation illustrates this pattern.

    >>> run, sys_path = sys_path_for_op(
    ...     "pythonpath-env",
    ...     flags={"path": project.cwd})

    >>> sys_path[0] in ("", run.dir), (sys_path[0], run.dir)
    (True, ...)

    >>> sys_path[1:3]
    ['.../samples/projects/pythonpath', '.../.guild/sourcecode']

Note in this case the project directory, which we specify by way of
the `path` flag (this is used to set the `PYTHONPATH` env by the
operation) is the first non-empty path entry.

    >>> sys_path[1] == project.cwd, sys_path[1], project.cwd
    (True, ...)

## Disabling source code

When `sourcecode` is disabled, Guild omits the default run source code
directory from the Python path. We use the `sourcecode-disabled` to
illustrate.

When we run `sourcecode-disabled` without otherwise providing a path
to the source code, we get an error.

    >>> try:
    ...     sys_path_for_op("sourcecode-disabled")
    ... except RunError as e:
    ...     print(e.output)
    ... else:
    ...     assert False
    guild: No module named sys_path_test

Because we disabled source code copies for the operation, we must
provide the location of the `sys_path_test` module via the
`PYTHONPATH` env variable.

    >>> run, sys_path = sys_path_for_op(
    ...     "sourcecode-disabled",
    ...     extra_env={"PYTHONPATH": project.cwd})

    >>> sys_path[0] in ("", run.dir), (sys_path[0], run.dir)
    (True, ...)

The run directory is not in the path.

    >>> any([run.dir in p for p in sys_path]), run.dir, sys_path
    (False, ...)

The project directory is.

    >>> project.cwd in sys_path, project.cwd, sys_path
    (True, ...)

## Python path and sub-directories

When an operation specifies a subdirectory for `main` in the format
`SUBDIR/MODULE`, Guild includes the subdirectory path in the Python
system path. The `subdir` operation illustrates this. It's `main` spec
is `src/sys_path_test2.py`.

    >>> run, sys_path = sys_path_for_op("subdir")

    >>> sys_path[0]
    '.../.guild/sourcecode/src'

    >>> sys_path[1] in ("", run.dir), (sys_path[0], run.dir)
    (True, ...)

    >>> sys_path[2]
    '.../.guild/sourcecode'

Note in this case Guild inserts the module subdirectory in the front
of the list. The rest of the path is as it is normally.

    >>> sys_path[0] == run.guild_path("sourcecode", "src"), run.dir, sys_path
    (True, ...)

    >>> sys_path[2] == run.guild_path("sourcecode"), run.dir, sys_path
    (True, ...)

Note that `src` is a subdirectory in this case and not a Python
package. See the next section for Guild's treament of packages
specified in `main`.

## Python packages

When a Python package is specified in `main` ---
e.g. `pkg.sys_path_test3` --- Guild does not need to insert additional
system paths as with subdirectories (see above). The `pkg` operation
illustrates.

    >>> run, sys_path = sys_path_for_op("pkg")

    >>> sys_path[0] in ("", run.dir), (sys_path[0], run.dir)
    (True, ...)

    >>> sys_path[1]
    '.../.guild/sourcecode'

Here's the source code structure for the run:

    >>> find(run.guild_path("sourcecode"), ignore="*.pyc")
    guild.yml
    pkg/__init__.py
    pkg/sys_path_test3.py
    src/sys_path_test2.py
    src2/pkg2/__init__.py
    src2/pkg2/sys_path_test4.py
    sys_path_test.py

`pkg` contains `__init__.py` and is therefore a Python package. The
location that must appear in the Python system path is therefore the
`.guild/sourcecode` run subdirectory,

See the below for an example of running a package under a
subdirectory.

## Python packages with subdirectories

This test shows Guild's behavior when a package module is located
within a project subdirectory. We use the `pkg-with-subdir`
operation to illustrate.

    >>> run, sys_path = sys_path_for_op("pkg-with-subdir")

    >>> sys_path[0]
    '.../.guild/sourcecode/src2'

    >>> sys_path[1] in ("", run.dir), (sys_path[0], run.dir)
    (True, ...)

    >>> sys_path[2]
    '.../.guild/sourcecode'

This example follows the `subdir` example above.

    >>> find(run.guild_path("sourcecode"), ignore="*.pyc")
    guild.yml
    pkg/__init__.py
    pkg/sys_path_test3.py
    src/sys_path_test2.py
    src2/pkg2/__init__.py
    src2/pkg2/sys_path_test4.py
    sys_path_test.py


In order to run the `pkg2.sys_path_test4` module, the `src2`
subdirectory must be included in the Python system path. In this case,
that directory is inserted at the beginning of the system path list.