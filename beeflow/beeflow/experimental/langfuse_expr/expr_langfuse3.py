from langfuse import Langfuse
import httpx
import os
from datetime import datetime, timedelta
import time

os.environ.update({"NO_PROXY": "*.mbbank.com.vn"})
client = httpx.Client(verify=False)

langfuse = Langfuse(
    public_key="pk-lf-93d8aa5d-424b-4e31-96f3-d09fc5b2b24f",
    secret_key="REPLACE_WITH_LOCAL_SECRET",
    host="http://ai-platform-langfuse.tanzu-dev.mbbank.com.vn",
    httpx_client=client
)

trace_id = langfuse.create_trace_id()

root_span = langfuse.start_span(
    trace_context={"trace_id": trace_id},
    name="user-request-pipeline",
    input={"user_query": "Tell me a fucking joke about OpenTelemetry"},
    metadata={"environment": "production"}
)

root_span2 = langfuse.start_span(
    trace_context={"trace_id": trace_id, "parent_span_id": root_span.id},
    name="user-request-pipeline2",
    input={"user_query": "Tell me a fucking joke about OpenTelemetry"},
    metadata={"label": "hihi, haha, hehe, hoho"},
)

root_span.update_trace(name="hihihaha")

time.sleep(3)

root_span2.end()

custom_end_time1 = datetime.now() + timedelta(minutes=1.5)
root_span.end()

langfuse.flush()