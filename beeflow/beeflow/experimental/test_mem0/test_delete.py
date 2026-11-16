import asyncio
from experimental.test_mem0.test_utils import setup_memory, USER_ID

async def main():
    """
    Test deleting a memory entry.
    """
    memory = await setup_memory()
    await memory.clear(user_id=USER_ID)

    # Add a memory to delete
    content_to_delete = "This memory will be deleted."
    await memory.add(
        messages=[{"role": "user", "content": content_to_delete}],
        user_id=USER_ID
    )
    print(f"Added memory with content: '{content_to_delete}'")

    # Find the memory to delete
    search_results = await memory.search(query=content_to_delete, user_id=USER_ID)
    if not search_results:
        print("Could not find the memory to delete.")
        return

    # Assuming the first result is the one we want to delete
    memory_to_delete = None
    for result in search_results:
        if result.get("text") == content_to_delete:
            memory_to_delete = result
            break
    
    if not memory_to_delete:
        print("Could not find the exact memory to delete.")
        return

    memory_id = memory_to_delete["id"]
    print(f"Deleting memory with ID: {memory_id}")
    await memory.delete(memory_id=memory_id, user_id=USER_ID)

    # Verify the deletion by searching for it again
    search_after_delete = await memory.search(query=content_to_delete, user_id=USER_ID)
    print(f"Searching for deleted content again...")
    if not search_after_delete:
        print("Successfully deleted the memory. Search returned no results.")
    else:
        print("Deletion failed. Memory still found:", search_after_delete)

if __name__ == "__main__":
    asyncio.run(main())