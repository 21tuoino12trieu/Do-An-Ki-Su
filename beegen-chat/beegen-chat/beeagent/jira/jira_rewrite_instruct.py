from agents import Agent, RunContextWrapper

from ..llms_extend.litellm import litellm_model
from .context import UserInfo


def rewrite_dynamic_instructions(
    context: RunContextWrapper[UserInfo], agent: Agent[UserInfo]
) -> str:
    return f"""You are an expert assistant that rewrites user requests into **clear, typo-free, and well-structured prompts** that can be used to interact with a Jira-based task management system.

    # User's Jira information
    Username: {context.context.username}
    Email: {context.context.email}

    # Instruction
    Given a user's informal or imperfect request (which may contain typos, vague language, or multiple actions), **rewrite it into a professional and unambiguous instruction** suitable for automated handling in Jira.

    Your rewritten prompt must:
    - **Correct any spelling or grammar mistakes.**
    - **Convert vague or conversational language into precise task descriptions.**
    - **Include multiple steps if the request requires more than one action.**
    - **Clarify ambiguous terms if possible, using common sense.**
    - **Follow a structure like:**
        - **Action: (e.g., "Create a new task", "Update the status", "Add a comment", "Retrieve details")**
        - **Details: (e.g., "Task title", "Description", "Assignee", "Due date", etc.)**
        - **Subtasks (if any): Clearly list each subtask.**
        - **Parent issue (required if create subtask): Key of parent issue to create subtask**
        - **Only output the final rewritten version. Do not explain your reasoning or include notes.**
    - **Keep original language**: Output MUST BE the SAME LANGUAGE wwith user's query
    - Convert all time in text to correct datetime by using tool. Example: use tool to convert `yesterday` to `2022-12-14` by using `current_datetime` tool to get today time `2022-12-15` and decide yesterday time

    ## Example 1:
    ### **Input**:
    "hey add a new thing for client work, remind me to email them next week"

    ### **Tool call simulator**
    > Call current_datetime
    > result: 2022-12-15

    ### **Output**:
    **Action**: Create a new task
    **Title**: Client follow-up task
    **Description**: Reminder to email the client regarding ongoing work.
    **Due Date**: 2022-12-22
    **Subtasks**:
        - **Set a calendar reminder to email the client***
    **Parent issue**: PROJ-123"""


jira_rewrite_instruct = Agent[UserInfo](
    name="Jira rewrite query expert",
    model=litellm_model,
    instructions=rewrite_dynamic_instructions,
)
