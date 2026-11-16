import asyncio
from experimental.test_mem0.test_utils import setup_memory, USER_ID

async def main():
    """
    Test updating a memory entry.
    """
    memory = await setup_memory()

    # Add a memory to update
    add_result = await memory.add(
        messages=[{"role": "user", "content": "Tôi còn thích phim trinh thám"}],
        user_id=USER_ID
    )
    print("Added memory for update test:", add_result)

    # In a real scenario, you'd get the memory_id from a search or get_history call
    # For this test, we'll assume the last added memory is the one to update.
    # This is a simplification. A robust test would search for the specific memory.
    history = await memory.get_history(user_id=USER_ID)
    if not history:
        print("No history found to update.")
        return

    # Find a memory to update. Let's find one with a 'summary'.
    memory_to_update = None
    for mem in history:
        if mem.get("summary"):
            memory_to_update = mem
            break
    
    if not memory_to_update:
        print("No memory with a summary found to update.")
        # Let's try to find a memory with 'raw_text'
        for mem in history:
            if mem.get("raw_text"):
                memory_to_update = mem
                break

    if memory_to_update:
        memory_id = memory_to_update["id"]
        new_data = "This is the updated content."
        
        print(f"Updating memory {memory_id} with new data: '{new_data}'")
        await memory.update(memory_id=memory_id, data=new_data, user_id=USER_ID)
        
        # Verify the update by searching for the updated content
        updated_memories = await memory.search(query=new_data, user_id=USER_ID)
        print("Search result after update: ", updated_memories)
    else:
        print("Could not find a suitable memory to update.")


if __name__ == "__main__":
    asyncio.run(main())