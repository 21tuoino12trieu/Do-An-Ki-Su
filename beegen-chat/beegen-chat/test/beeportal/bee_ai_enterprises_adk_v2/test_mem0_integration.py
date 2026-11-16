"""Integration test: mem0 + Milvus + LiteLLM Proxy connectivity."""
import asyncio
import os
import sys

# Load .env from the project root
from dotenv import load_dotenv
load_dotenv(dotenv_path=r"d:\work\projects\llm\beegen-chat\.env", override=False)

print("=" * 60)
print("ENV CHECK")
print("=" * 60)
for key in [
    "MEM0_MILVUS_URI", "MEM0_MILVUS_USERNAME", "MEM0_MILVUS_PASSWORD",
    "MEM0_MILVUS_DB", "MEM0_EMBED_BASE_URL", "MEM0_EMBED_MODEL",
    "MEM0_EMBED_DIMS", "AIE_LLM_API_KEY", "AIE_LLM_BASE_URL",
    "AIE_LLM_LOCAL_MODEL",
]:
    v = os.environ.get(key, "<MISSING>")
    if "KEY" in key or "PASSWORD" in key:
        v = v[:8] + "..." if len(v) > 8 else v
    print(f"  {key}: {v}")

print("\n" + "=" * 60)
print("STEP 1: Initialize MemoryManager")
print("=" * 60)
try:
    from beeportal.bee_ai_enterprises_adk_v2.utils.memory_manager import get_memory_manager
    mgr = get_memory_manager()
    print("  OK - MemoryManager initialized")
except Exception as e:
    print(f"  FAILED: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("STEP 2: add_memory (test user)")
print("=" * 60)

async def test_add():
    try:
        await mgr.add_memory(
            user_query="Toi ten Cuong, toi lam o phong AI Center",
            answer="Chao ban Cuong! Rat vui duoc gap ban. Ban can toi ho tro gi a?",
            user_id="test_user_mem0",
            session_id="test_session_001",
        )
        print("  OK - add_memory completed")
    except Exception as e:
        print(f"  FAILED: {e}")
        import traceback; traceback.print_exc()

asyncio.run(test_add())

print("\n" + "=" * 60)
print("STEP 3: search_memory (test user)")
print("=" * 60)

async def test_search():
    try:
        result = await mgr.search_memory(
            query="Toi ten gi?",
            user_id="test_user_mem0",
            session_id="test_session_001",
        )
        print(f"  Search result:\n{result}")
        if result:
            print("  OK - found memories")
        else:
            print("  WARNING - no memories found (may need time to index)")
    except Exception as e:
        print(f"  FAILED: {e}")
        import traceback; traceback.print_exc()

asyncio.run(test_search())

print("\n" + "=" * 60)
print("ALL DONE")
print("=" * 60)
