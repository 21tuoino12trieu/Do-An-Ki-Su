from langfuse import Langfuse
import os

os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-93d8aa5d-424b-4e31-96f3-d09fc5b2b24f"
os.environ["LANGFUSE_SECRET_KEY"] = "REPLACE_WITH_LOCAL_SECRET"
os.environ["LANGFUSE_HOST"] = "http://ai-platform-langfuse.tanzu-dev.mbbank.com.vn"
os.environ['NO_PROXY'] = "NO_PROXY"

langfuse = Langfuse()

langfuse.auth_check()
langfuse.trace(id="abc")
langfuse.flush()