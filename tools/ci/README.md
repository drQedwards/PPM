# tools/ci — batch build check

`batch_build_check.py` compiles every tracked C, C++, Cython and CUDA unit in the repo, plus a few
link, run and Makefile targets. It writes a per-unit table (status, warning count, first error,
sha256) to stdout and to the GitHub step summary, and saves the same data as JSON
(`batch-build-results.json`). The `batch-build` workflow runs it on every push and PR.

```bash
sudo apt-get install -y build-essential python3-dev libcurl4-openssl-dev   # Ubuntu/Debian
pip install cython numpy
python tools/ci/batch_build_check.py
```

## Policy

- **Required** units are listed at the top of the script (`REQUIRED_C`, `REQUIRED_CXX`,
  `REQUIRED_PYX`, `REQUIRED_LINKS`, `REQUIRED_MAKE`). Each one must compile with
  `-Wall -Wextra`, and every listed link or make target must succeed. A required failure,
  or a required file that has gone missing, exits 1.
- Every other unit is **informational**. It is compiled and reported, but it never fails the job.

Known informational failures at the time this was added:

| unit | reason |
|---|---|
| `CLI/CLI.c` | includes `ppm_core.h`, which does not exist in the repo (needs a design decision) |
| `Ppm-lib/Pypm.c` | needs the external `toml.h` (tomlc99), which is not vendored |
| `Torch-lib/Torch_plugin.c` | calls `torch_install` and other functions that are never declared |
| `Panda-lib/Pandas_bridge.pyx` | uses raw CPython API names that it never declares |
| `*.cu` | nvcc is not available on the runner, so these are skipped |

When you fix one of these, move it into the matching `REQUIRED_*` list in the same PR.
Workflow edits are not needed for that.
