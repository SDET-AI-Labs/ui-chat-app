from .settings import settings

# Optional: HF backend will be added later; avoid import errors before adapter exists.
try:
	from .hf_infer import HFBackend  # type: ignore
except Exception:  # pragma: no cover - optional import
	HFBackend = None  # sentinel to indicate not available yet

