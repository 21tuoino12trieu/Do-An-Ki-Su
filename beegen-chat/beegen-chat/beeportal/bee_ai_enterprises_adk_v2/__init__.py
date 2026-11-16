# -*- coding: utf-8 -*-

__all__ = ["BeeAiEnterprisesADK"]

def __getattr__(name: str):
    if name == "BeeAiEnterprisesADK":
        from .agent import BeeAiEnterprisesADK
        return BeeAiEnterprisesADK
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
