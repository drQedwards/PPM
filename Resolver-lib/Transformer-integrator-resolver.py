# ppm/resolver.py (inside resolve(requests))
from ppm.hooks.transformers_policy import detect_backend  # noqa: F401


def expand_with_policy(reqs, cfg=None, add_requirement=None, user_gpu_flag=None):
    # If cfg or add_requirement are not provided, behave as a no-op for backward compatibility.
    if cfg is None or add_requirement is None:
        return reqs
    # If user asked for transformers (explicitly or via ensure), add torch.
    names = {r.name for r in reqs}
    if "transformers" in names and "torch" not in names:
        backend = detect_backend(user_gpu_flag)
        # Pin preferred versions from config; allow override via CLI.
        torch_spec = f"torch=={cfg.torch_prefer}"
        add_requirement(torch_spec, extra_index=backend.index, policy_tag=backend.name)
    return reqs
