import contextvars

_current_graph = contextvars.ContextVar("current_graph")