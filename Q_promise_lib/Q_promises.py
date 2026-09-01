"""Python façade for the PMLL Promise / Continuation Library.

The Cython QMemNode seed is retired. Prefer the C API via ctypes against
``libqpromise.so`` / ``q_promises.so``, or embed ``qpromise.h`` directly.

See Q_promise_lib/README.md for the retrieve→compute→resolve→memory loop.
"""

__all__ = ["__doc__"]
__version__ = "1.0.0"
