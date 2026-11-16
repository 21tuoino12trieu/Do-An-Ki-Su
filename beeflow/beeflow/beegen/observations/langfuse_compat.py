"""Giữ giao diện trace của Beeflow, xuất observation bằng SDK 4.7.1/OTel.

SDK được ghim vì phần replay thời gian dùng tracer/wrapper nội bộ của SDK.
Không gọi endpoint batch ingestion v2 đã cũ.
"""

from datetime import datetime
import time

from langfuse import propagate_attributes
from langfuse._client.attributes import LangfuseOtelSpanAttributes
from opentelemetry import trace


def _nanoseconds(value):
    if isinstance(value, datetime):
        return int(value.timestamp() * 1_000_000_000)
    return None


class WorkflowObservation:
    def __init__(self, client, observation, attributes):
        self.client = client
        self.observation = observation
        self.attributes = attributes

    def span(self, **data):
        return record_observation(self.client, "span", data, parent=self)

    def generation(self, **data):
        return record_observation(self.client, "generation", data, parent=self)


def record_observation(client, kind, data, *, parent=None, request_id=None, attributes=None):
    data = dict(data)
    attributes = parent.attributes if parent is not None else (attributes or {})
    start = _nanoseconds(data.pop("start_time", None)) or time.time_ns()
    end = _nanoseconds(data.pop("end_time", None)) or time.time_ns()
    end = max(start, end)
    data.pop("contain_generation", None)
    name = data.pop("name", "workflow")
    usage = data.pop("usage", None)
    if usage is not None and hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if isinstance(usage, dict):
        mapped = {}
        for key, value in usage.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            key = {"prompt_tokens": "input", "input_tokens": "input",
                   "completion_tokens": "output", "output_tokens": "output",
                   "total_tokens": "total"}.get(key, key)
            mapped[key] = int(value)
        if mapped:
            data["usage_details"] = mapped
    allowed = {"input", "output", "metadata", "version", "level", "status_message",
               "completion_start_time", "model", "model_parameters", "usage_details",
               "cost_details", "prompt"}
    payload = {key: value for key, value in data.items() if key in allowed}

    if parent is not None:
        parent_span = parent.observation._otel_span
    else:
        # Cùng cách tạo parent context như SDK start_observation(trace_context=...).
        trace_id = int(client.create_trace_id(seed=request_id), 16)
        remote = trace.NonRecordingSpan(trace.SpanContext(
            trace_id=trace_id, span_id=1, is_remote=True,
            trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
        ))
        parent_span = remote

    with trace.use_span(parent_span, end_on_exit=False), propagate_attributes(**attributes):
        span = client._otel_tracer.start_span(name=name, start_time=start)
        if parent is None:
            span.set_attribute(LangfuseOtelSpanAttributes.AS_ROOT, True)
        try:
            observation = client._create_observation_from_otel_span(
                otel_span=span, as_type=kind, **payload,
            )
        finally:
            span.end(end_time=end)
    return WorkflowObservation(client, observation, attributes)
