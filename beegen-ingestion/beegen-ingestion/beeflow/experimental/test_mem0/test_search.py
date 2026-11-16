import asyncio
from experimental.test_mem0.test_utils import setup_memory, USER_ID, MESSAGES

async def main():
    """
    Test searching for memories.
    """
    memory = await setup_memory()
    #add data 
    result = await memory.add(messages=MESSAGES, user_id=USER_ID, metadata={"category": "phim"})
    print("Add result: ", result)

    # Search for related memories
    query = "tôi thích xem phim kinh dị không?"
    related_memories = await memory.search(query=query, user_id=USER_ID)
    print(f"Searching for: '{query}'")
    print("Search result: ", related_memories)

if __name__ == "__main__":
    asyncio.run(main())