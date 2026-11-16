from agents import Agent, RunContextWrapper

from ..llms_extend.litellm import litellm_model
from .context import UserInfo


def info_dynamic_instructions(
    context: RunContextWrapper[UserInfo], agent: Agent[UserInfo]
) -> str:
    return f"""Use tool if needed to gathering all information that related to query like username, issue key, issue type,...
            Only add information and keep original query, do not delete or edit original query.
            This is important step because some Jira can have different name like Sub-Tasks, Subtask, Subtasks,...
            
            # User's Jira information
            Username: {context.context.username}
            Email: {context.context.email}

            # Instruction: 
                - If user want to create issue, use tool jira_search_issueTypes to search that issue and get correct issuetype's name then add to original message. 
                - NEVER use any tool that add/edit/delete anything. ONLY use tool to search or get informations.
                - After use tool, add correct information from tool to original query
            """


jira_info_gather = Agent[UserInfo](
    name="Jira information gathering",
    model=litellm_model,
    instructions=info_dynamic_instructions
)
