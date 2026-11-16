import asyncio

from requests import session
from experimental.test_mem0.test_utils import setup_memory, USER_ID, MESSAGES

async def main():
    """
    Test retrieving message history.
    """
    memory = await setup_memory()

    ID = "c5a8f494-7c88-4948-b582-9f00744e8c9d"

    # Add data to have a history
    result = await memory.add(messages=MESSAGES, user_id=USER_ID, metadata={"category": "phim"}, session_id= ID)
    print("Add result: ", result)

    # Retrieve the history
    history = await memory.get_history(session_id="c5a8f494-7c88-4948-b582-9f00744e8c9d")
    print("Retrieved history: ", history)

if __name__ == "__main__":
    asyncio.run(main())