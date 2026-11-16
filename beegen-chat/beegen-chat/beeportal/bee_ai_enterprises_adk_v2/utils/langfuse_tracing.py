# -*- coding: utf-8 -*-
"""Langfuse OpenTelemetry tracing setup cho bee_ai_enterprises_adk_v2.

Tham khảo pattern từ beegen-agent/app/logs/setup.py.
Module này khởi tạo:
  - Langfuse client với OpenTelemetry exporter
  - GoogleADKInstrumentor để tự động capture traces/spans/generations
  - Monkey-patches cho compatibility với phiên bản ADK hiện tại

QUAN TRỌNG: Module này phải được gọi SAU khi load_dotenv() đã nạp env vars,
và TRƯỚC khi Runner.run_async() chạy.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_tracing_initialized = False


def setup_langfuse_tracing() -> Optional[object]:
    """Khởi tạo Langfuse OTel tracing cho Google ADK.

    Idempotent — gọi nhiều lần sẽ chỉ khởi tạo 1 lần duy nhất.

    Returns:
        Langfuse client nếu khởi tạo thành công, None nếu thất bại hoặc bị disabled.
    """
    global _tracing_initialized

    if _tracing_initialized:
        return None

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST")
    tracing_enabled = os.getenv("LANGFUSE_TRACING_ENABLED", "True")

    if not host or not public_key or not secret_key:
        logger.info(
            "[Langfuse Tracing] Disabled: LANGFUSE credentials or host missing"
        )
        _tracing_initialized = True
        return None

    if tracing_enabled.lower() in ("false", "0", "no"):
        logger.info("[Langfuse Tracing] Disabled via LANGFUSE_TRACING_ENABLED=False")
        _tracing_initialized = True
        return None

    # --- Configure logfire (OTel provider, send_to_logfire=False) ---
    try:
        import logfire

        logfire.configure(
            service_name="langfuse-adk-v2",
            send_to_logfire=False,
            scrubbing=False,
            console=False,
            min_level="warning",
        )
    except ImportError:
        logger.warning(
            "[Langfuse Tracing] logfire not installed — "
            "continuing without logfire configuration"
        )
    except Exception as e:
        logger.warning("[Langfuse Tracing] logfire.configure() failed: %s", e)

    # --- Init Langfuse client and OpenTelemetry Exporter ---
    try:
        from langfuse import Langfuse
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        import base64

        langfuse = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            enabled=tracing_enabled.lower() not in ("false", "0", "no"),
        )
        
        # Configure OpenTelemetry exporter manually for langfuse < 3.x
        if tracing_enabled.lower() not in ("false", "0", "no"):
            auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
            otlp_endpoint = f"{host.rstrip('/')}/api/public/otel/v1/traces"
            
            exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                headers={"Authorization": f"Basic {auth}"}
            )
            
            tracer_provider = trace.get_tracer_provider()
            if hasattr(tracer_provider, "add_span_processor"):
                tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info("[Langfuse Tracing] OTLPSpanExporter attached to Langfuse API")
            else:
                logger.warning("[Langfuse Tracing] Could not attach OTLPSpanExporter: invalid tracer_provider")
                
    except Exception as e:
        logger.error("[Langfuse Tracing] Failed to setup Langfuse/OTel export: %s", e)

    # --- Add custom SpanProcessor to rename root trace and set tags ---
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import SpanProcessor
        class RootTraceRenamerProcessor(SpanProcessor):
            def on_start(self, span, parent_context=None):
                try:
                    if span.name and span.name.lower().startswith("invocation"):
                        if hasattr(span, "update_name"):
                            span.update_name("bee_ai_enterprises:adk_v2")
                        
                        # Set tags right at start when span is still recording
                        if hasattr(span, "set_attribute"):
                            span.set_attribute("langfuse.tags", ["adk-v2", "bee-ai-enterprises"])
                except Exception:
                    pass

            def on_end(self, span):
                try:
                    attrs = span._attributes or {}
                    modified = False
                        
                    # 2. Map ADK native attributes to standard Langfuse I/O
                    # LLM request/response
                    if "gcp.vertex.agent.llm_request" in attrs and "input.value" not in attrs:
                        attrs["input.value"] = str(attrs["gcp.vertex.agent.llm_request"])
                        modified = True
                    if "gcp.vertex.agent.llm_response" in attrs and "output.value" not in attrs:
                        attrs["output.value"] = str(attrs["gcp.vertex.agent.llm_response"])
                        modified = True
                        
                    # Tool call args/response
                    if "gcp.vertex.agent.tool_call_args" in attrs and "input.value" not in attrs:
                        attrs["input.value"] = str(attrs["gcp.vertex.agent.tool_call_args"])
                        modified = True
                    if "gcp.vertex.agent.tool_response" in attrs and "output.value" not in attrs:
                        attrs["output.value"] = str(attrs["gcp.vertex.agent.tool_response"])
                        modified = True
                        
                    if modified and hasattr(span, "_attributes"):
                        span._attributes = attrs
                except Exception:
                    pass

        tracer_provider = trace.get_tracer_provider()
        tracer_provider.add_span_processor(RootTraceRenamerProcessor())
        logger.info("[Langfuse Tracing] RootTraceRenamerProcessor added to TracerProvider")
    except Exception as e:
        logger.warning("[Langfuse Tracing] Failed to add RootTraceRenamerProcessor: %s", e)

    # --- Add monkey-patches to inject input/output into structural spans ---
    try:
        from opentelemetry import trace
        import functools
        from google.adk.runners import Runner
        from google.adk.agents.base_agent import BaseAgent
        from google.adk.workflow._base_node import BaseNode

        def extract_input_str(args, kwargs):
            ctx = kwargs.get("invocation_context") or kwargs.get("context")
            if not ctx and args:
                for arg in args:
                    if hasattr(arg, "new_message"):
                        ctx = arg
                        break
            if ctx and getattr(ctx, "new_message", None):
                try:
                    return "".join(p.text for p in ctx.new_message.parts if p.text)
                except Exception:
                    return str(ctx.new_message)
            
            if "node_input" in kwargs:
                node_input = kwargs["node_input"]
                if isinstance(node_input, str):
                    return node_input
                elif hasattr(node_input, "content") and hasattr(node_input.content, "parts"):
                    try:
                        return "".join(p.text for p in node_input.content.parts if p.text)
                    except Exception:
                        pass
                return str(node_input)
                
            return kwargs.get("input_str", "")

        def make_io_patch(original_func, is_root=False):
            @functools.wraps(original_func)
            async def patched_func(self, *args, **kwargs):
                input_str = extract_input_str(args, kwargs)
                # Fallback for runner
                if is_root and not input_str:
                    msg = kwargs.get("new_message")
                    if msg:
                        try:
                            input_str = "".join(p.text for p in msg.parts if p.text)
                        except Exception:
                            input_str = str(msg)
                            
                final_output = ""
                async for event in original_func(self, *args, **kwargs):
                    span = trace.get_current_span()
                    if span and span.is_recording():
                        if input_str and not span._attributes.get("input.value"):
                            span.set_attribute("input.value", input_str)
                        
                        if getattr(event, "output", None):
                            final_output = str(event.output)
                        elif getattr(event, "content", None) and getattr(event.content, "parts", None):
                            final_output = "".join(p.text for p in event.content.parts if p.text)
                        elif isinstance(event, str):
                            final_output = event
                            
                        if final_output:
                            span.set_attribute("output.value", final_output)
                    yield event
            return patched_func

        Runner.run_async = make_io_patch(Runner.run_async, is_root=True)
        BaseNode._run_impl = make_io_patch(BaseNode._run_impl)
        BaseAgent._run_async_impl = make_io_patch(BaseAgent._run_async_impl)
        BaseAgent._run_live_impl = make_io_patch(BaseAgent._run_live_impl)
        
        logger.info("[Langfuse Tracing] Monkey patches applied to inject I/O into structural spans")
    except Exception as e:
        logger.warning("[Langfuse Tracing] Failed to apply monkey patches: %s", e)

    # --- Setup GoogleADKInstrumentor with compatibility patches ---
    try:
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor

        # Monkey patch: bypass AttributeError on _patch_trace_tool_call
        # cho compatibility với phiên bản ADK hiện tại
        original_patch_trace_tool_call = GoogleADKInstrumentor._patch_trace_tool_call

        def safe_patch_trace_tool_call(self):
            try:
                original_patch_trace_tool_call(self)
            except AttributeError as e:
                logger.warning(
                    "[Langfuse Tracing] Could not patch trace_tool_call "
                    "(not supported in this ADK version): %s",
                    e,
                )

        GoogleADKInstrumentor._patch_trace_tool_call = safe_patch_trace_tool_call

        # Monkey patch: bypass ImportError on _disable_existing_tracers
        original_disable_existing_tracers = (
            GoogleADKInstrumentor._disable_existing_tracers
        )

        def safe_disable_existing_tracers(self):
            try:
                original_disable_existing_tracers(self)
            except ImportError as e:
                logger.warning(
                    "[Langfuse Tracing] Could not disable existing tracers "
                    "(not supported in this ADK version): %s",
                    e,
                )

        GoogleADKInstrumentor._disable_existing_tracers = (
            safe_disable_existing_tracers
        )

        # Instrument
        GoogleADKInstrumentor().instrument()
        logger.info("[Langfuse Tracing] GoogleADKInstrumentor activated")
    except ImportError:
        logger.info("[Langfuse Tracing] openinference-instrumentation-google-adk not installed. Using ADK native tracing.")
    except Exception as e:
        logger.warning("[Langfuse Tracing] GoogleADKInstrumentor instrumentation failed: %s", e)

    # --- Auth check ---
    try:
        import httpx

        auth_ok = langfuse.auth_check()
        if auth_ok:
            logger.info(
                "[Langfuse Tracing] Client authenticated successfully → %s", host
            )
        else:
            logger.warning(
                "[Langfuse Tracing] Authentication failed. "
                "Check credentials and host."
            )
    except ImportError:
        logger.info("[Langfuse Tracing] httpx not available — auth check skipped")
    except Exception as exc:
        logger.warning("[Langfuse Tracing] Auth check skipped due to error: %s", exc)

    _tracing_initialized = True
    return langfuse
