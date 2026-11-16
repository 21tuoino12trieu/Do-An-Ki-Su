import asyncio
from experimental.test_mem0.test_utils import setup_memory, USER_ID, MESSAGES

async def main():
    """
    Test adding messages to the memory.
    """
    memory = await setup_memory()

    # Clear any existing memories for the user
    await memory.clear(user_id=USER_ID)
    print(f"Memory cleared for user: {USER_ID}")

    # Add messages to the memory
    result = await memory.add(messages=MESSAGES, user_id=USER_ID, metadata={"category": "phim"})
    print("Add result: ", result)

if __name__ == "__main__":
    asyncio.run(main())