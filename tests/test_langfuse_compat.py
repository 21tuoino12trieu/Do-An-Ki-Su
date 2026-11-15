"""Kiểm tra adapter bằng exporter trong RAM, không kết nối Cloud."""

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "beeflow" / "beeflow"))

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from beegen.observations.bee_langfuse import BeeLangfuse


class LangfuseCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.exporter = InMemorySpanExporter()
        self.client = BeeLangfuse(
            public_key="pk-lf-offline-" + uuid.uuid4().hex,
            secret_key="offline-only", host="https://example.invalid",
            tracer_provider=TracerProvider(), span_exporter=self.exporter,
        )
        self.start = datetime.now(timezone.utc) - timedelta(seconds=2)
        self.end = self.start + timedelta(seconds=1)

    def tearDown(self):
        self.client.shutdown()

    def root(self):
        return self.client.trace(
            id="fixture-workflow", name="fixture", user_id="fixture-user",
            session_id="fixture-session", start_time=self.start, end_time=self.end,
            input={"value": 1}, output={"result": 2}, contain_generation=False,
        )

    def spans(self):
        self.client.flush()
        return {span.name: span for span in self.exporter.get_finished_spans()}

    def test_parent_child_timestamps_and_attributes(self):
        root = self.root()
        root.span(name="child", start_time=self.start, end_time=self.end, output={"ok": True})
        spans = self.spans()
        parent, child = spans["fixture"], spans["child"]
        self.assertEqual(child.context.trace_id, parent.context.trace_id)
        self.assertEqual(child.parent.span_id, parent.context.span_id)
        self.assertEqual(parent.start_time, int(self.start.timestamp() * 1e9))
        self.assertEqual(parent.end_time, int(self.end.timestamp() * 1e9))
        self.assertEqual(child.attributes["user.id"], "fixture-user")
        self.assertEqual(child.attributes["session.id"], "fixture-session")
        self.assertTrue(parent.attributes["langfuse.internal.as_root"])

    def test_generation_usage_is_preserved_without_model_call(self):
        root = self.root()
        root.generation(
            name="generation", model="fixture-no-model-call",
            start_time=self.start, end_time=self.end,
            usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        )
        generation = self.spans()["generation"]
        self.assertEqual(generation.attributes["langfuse.observation.type"], "generation")
        usage = json.loads(generation.attributes["langfuse.observation.usage_details"])
        self.assertEqual(usage, {"input": 2, "output": 3, "total": 5})

    def test_error_level_output_and_metadata(self):
        root = self.root()
        root.span(
            name="failure", level="ERROR", output="fixture failure",
            metadata={"step": "check"}, start_time=self.start, end_time=self.end,
        )
        span = self.spans()["failure"]
        self.assertEqual(span.attributes["langfuse.observation.level"], "ERROR")
        self.assertIn("fixture failure", span.attributes["langfuse.observation.output"])


if __name__ == "__main__":
    unittest.main()
