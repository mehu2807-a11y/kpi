"""
Loads each task's modules in isolation so same-named files across tasks
(schemas.py appears in task5 AND task6; pipeline.py appears in task2 AND
task5) never collide in sys.modules. Usage:

    with scoped_task_dir(TASK5_DIR):
        import schemas as t5_schemas
        import pipeline as t5_pipeline
    # sys.path is restored, and only modules that were actually LOADED FROM
    # task_dir are purged from sys.modules -- hold onto the objects you need
    # (functions/classes), not the module references, since those bare names
    # get purged when the block exits.

Purging is scoped by file location (module.__file__ starting with task_dir),
NOT by "newly added to sys.modules during this block". An earlier version
used the latter and it's unsafe: numpy/scipy/sklearn lazily import
submodules (e.g. numpy.fft._pocketfft_umath) deep inside function calls --
not just at top-level `import numpy` time -- so a task's FIRST call to
IsolationForest.fit() can trigger a fresh numpy/scipy submodule import that
a naive before/after diff would treat as "belongs to this task" and delete.
numpy's C extensions cannot be reloaded once purged ("cannot load module
more than once per process"), which crashed the very first real gate-walk
test here. Filtering by file path fixes it at the root instead of patching
around it with a fixed pre-import list that the next lazy import could
still slip past.
"""
from __future__ import annotations
import sys
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def scoped_task_dir(task_dir: str):
    task_dir_str = str(Path(task_dir))          # OS-native form, for sys.path
    task_dir_path = Path(task_dir).resolve()     # for robust path comparison below
    before_names = set(sys.modules.keys())
    sys.path.insert(0, task_dir_str)
    try:
        yield
    finally:
        sys.path.remove(task_dir_str)
        added = set(sys.modules.keys()) - before_names
        for name in added:
            mod = sys.modules.get(name)
            origin = getattr(mod, "__file__", None)
            if not origin:
                continue
            # Compare as actual paths, not raw strings, so this works the
            # same on Windows (backslashes) as on Mac/Linux (forward
            # slashes). A plain str.startswith(task_dir + "/") -- the
            # original approach -- silently never matches on Windows,
            # since __file__ there uses "\" instead of "/": the purge below
            # would be skipped entirely, leaving the wrong task's
            # same-named module (e.g. schemas.py) cached in sys.modules for
            # every subsequent task to accidentally reuse.
            try:
                Path(origin).resolve().relative_to(task_dir_path)
            except ValueError:
                continue  # shared third-party/stdlib module -- leave it
            del sys.modules[name]
