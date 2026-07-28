"""No-op cost meter shim for crawler/smart_crawl.py."""


def record(*_args, **_kwargs) -> None:
    pass


def estimate_llm_cost_inr(*_args, **_kwargs) -> float:
    return 0.0
