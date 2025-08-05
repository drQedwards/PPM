#include <Python.h>
#include "panda_py.h"

static int run_py_snippet(const char *code) {
    Py_Initialize();
    int rc = PyRun_SimpleString(code);
    Py_Finalize();
    return rc;
}

int panda_install(int argc, char **argv) {
    /* build ‘pandas==VERSION’ or latest */
    const char *ver = (argc ? argv[0] : "pandas");
    char cmd[256];
    snprintf(cmd, sizeof cmd,
             "import pypm_internal as _i; _i.install('%s')", ver);
    return run_py_snippet(cmd);
}

int panda_cache_wheels(void) {
    return run_py_snippet(
        "import pypm_internal as _i; _i.cache(['pandas','numpy','python_dateutil','pytz'])");
}

int panda_csv_peek(const char *path) {
    char code[512];
    snprintf(code, sizeof code,
        "import pandas as pd, sys; "
        "df=pd.read_csv(r'%s', nrows=10); "
        "print(df.to_markdown()); "
        "print('\\n— dtypes —'); print(df.dtypes)",
        path);
    return run_py_snippet(code);
}

int panda_doctor(void) {
    return run_py_snippet(
        "import numpy, pandas, platform, sys; "
        "print('numpy', numpy.__version__, numpy.__config__.show()); "
        "print('pandas', pandas.__version__); "
        "print('platform', platform.platform()); "
        "sys.exit(0)");
}
