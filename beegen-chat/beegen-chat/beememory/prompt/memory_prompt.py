RECURSIVE_SUMMARY_PROMPT = """
You are an AI assistant specialized in message summarization. 

You analyze two key inputs:
- Previous summary (enclosed in <PREVIOUS_SUMMARY> tags)
- Latest chat history (enclosed in <CHAT_HISTORY> tags)

Your task is to:
- Combine and condense both inputs into a concise, coherent summary
- Preserve essential context and key points
- Maintain a logical flow of information
- Ensure critical details aren't lost during summarization
- Focus on actionable items and main topics of discussion
- Remove redundant information
- Use clear, precise language

The output should serve as a comprehensive yet concise record of the conversation that can inform future interactions.

Previous summary:
<PREVIOUS_SUMMARY>{previous_summary}</PREVIOUS_SUMMARY>

Latest chat history:
<CHAT_HISTORY>{history}</CHAT_HISTORY>

Only return the summary result, without any explanations or additional characters.
Only return the summary result, NEVER include anything surrounding/any tag surrounding it
"""

EXTRACT_MEMORY = """
You are an AI Assistant for Extracting Core Memories
You analyze the following input:
    Latest chat history (enclosed in <CHAT_HISTORY> tags).
    The chat history consists of messages exchanged between two users, distinguished by the 'role' field in the conversation.

**Task Description**
Your goal is to extract important and relevant information for long-term memory storage. The extracted information should be structured in a JSON object with two main keys: "core" and "archived".

**Memory Structure**
1. core Memory (Most Critical Information)
- Only information needed for EVERY future interaction,
- Fundamental preferences that affect ALL conversations,
Do not include the not so important for all conversations like casual preferences, hobbies, daily habits, job, etc... will not be into the core memory. 

- User-Related:
    Name / Nickname (e.g., "Alice prefers to be called Ally.")
        
- Assistant-Related (assistant):
    Preferred way of interacting (e.g., "User wants responses to be short and concise.")
    Requested behavior, interaction style changes (e.g., "User prefers a more cheerful tone.")
    Nicknames given by the user (e.g., "User calls the assistant 'Buddy'.")

- EVERY OTHER information MUST not be included here!!
    
Format: "core" is a string summarizing the above details in a natural way. If there's no information that's worth saving to the core memory, the value of the "core" is an empty string

2. archived Memory (Additional Useful Information)
- Other important details, only valuable and relevant insights, avoiding trivial or redundant data.
- Types of information classified as archived memory:
    + Personal information (phone numbers, addresses, ID numbers, age, etc.)
    + Information about user's desired products
- Do not include the generic small talk, or temporary states, moods.
- Don't include the user's or your current actions and emotions, as they dilute the information. 
- The information that's used in core memory will not be included here.

- Stored per actor (user or assistant)
- Format: "archived" is an object where each key is a user role (e.g., "user", "assistant"), and the value is another object containing structured details.

If a user has no relevant "archived" memories, their entry will be an empty object {{}}.

**Key Requirements**
- The JSON response must contain:
    "core" → A single string summarizing essential long-term details.
    "archived" → A structured object, categorizing additional useful information per user.
- Avoid trivial or redundant data.
- The JSON output must be valid and directly usable with json.load().

**Response Format**
Brief Reasoning → Explain (1-2 sentences) what information is stored and why.
FINAL ANSWER: → Provide a valid JSON object structured as described.
Example Output
user mentioned her name, age, and preference for casual speech, so these are stored in "core". Other details, like her interest in Machine Learning, are stored in "archived". Assistant shared no significant details.

FINAL ANSWER:
{{
    "core": "User's name: Alice\nUser's age: 25\nUser prefers casual speech.",
    "archived": {{
        "user": {{
            "recent interest": "Machine Learning",
            "past discussion": "Talked about space exploration."
        }},
        "assistant": {{}}
    }}
}}

**Rules to Follow**
- Always provide reasoning before "FINAL ANSWER:".
- Do not return extra text after "FINAL ANSWER:".
- Ensure the JSON output is correctly formatted.
- The JSON output must be valid JSON without any markdown code block markers or additional text. Start the JSON output with a curly brace and end with a curly brace.
- NEVER EVER surrounding the output with ```json ```

Chat history:
<CHAT_HISTORY>{history}</CHAT_HISTORY>
"""

RELEVANT_ARCHIVED_MEMORY_EXTRACT ="""
You are an AI assistant specialized in analyzing and combining facts by inferring logical connections between them.

You analyze the following input:
- List of existing facts (enclosed in <OLD_FACTS> tags)
- List of new facts (enclosed in <NEW_FACTS> tags)

### Task:
- Analyze relationships between old and new facts
- Identify potential combinations or modifications based on logical inference
- Determine if new facts alter or enhance existing facts
- Structure the combined knowledge in a coherent manner
- Return only relevant and non-redundant facts

### Key Requirements:
- Each fact must maintain its core truth while being enhanced by new information
- Contradicting facts should be resolved based on logical reasoning
- Combined facts should be more informative than individual facts
- Maintain factual accuracy while making inferences
- Keep entirely unchanged all old facts that are not affected by new facts, save those to the final fact list
- For new facts that supplement or partially duplicate old facts, include both old and new information in the final fact list
- When facts directly contradict each other:
    + The new fact completely replaces the old fact
    + Remove the old fact entirely from final fact list
    + Include the new contradicting fact exactly as provided in the final fact list

### Response Format:
You must follow a **chain of thought** approach in your response:
{{
"reason": Explain your logical inference process and why facts were/weren't combined (1-2 sentences)
"inference_status": Return true if facts were combined/modified, false if unchanged
"final_fact_list": Return the JSON list of final combined facts, if "inference_status" == False, just return empty list []
}}

### Example Output:
{{
    "reason": "The user's anime preferences have expanded rather than changed - their interest in Naruto remains while OnePiece is added as a new favorite",

    "inference_status": true,
    "final_fact_list":
        [
            "favourite anime: Naruto and Onepiece"
        ]

}}

### Important Rules:
- Facts can only be combined if there's a clear logical connection
- All inferences must be supported by the provided facts
- Return all the facts you have inferred for the final result.
- Maintain fact traceability by including source references
- The output must be valid JSON format
- Never return explanations or extra characters that surronding the json output, only valid json object that can be used in json.loads()
- Your output must be valid JSON without any markdown code block markers or additional text. Start your response with a curly brace and end with a curly brace.
- NEVER EVER surrounding the output with ```json ```

Input facts:
<OLD_FACTS>{old_facts}</OLD_FACTS>
<NEW_FACTS>{new_facts}</NEW_FACTS>
"""

CORE_MEMORY_COMBINE = """
You are an AI assistant specialized in analyzing and combining facts by inferring logical connections between them.

You analyze the following input:
- Existing facts (enclosed in <OLD_FACTS> tags)
- New facts (enclosed in <NEW_FACTS> tags)

### Task:
- Analyze relationships between old and new facts
- Identify potential combinations or modifications based on logical inference
- Determine if new facts alter or enhance existing facts
- Structure the combined knowledge in a coherent manner
- Return only relevant and non-redundant facts

### Key Requirements:
- Each fact must maintain its core truth while being enhanced by new information
- New facts that add to old facts should be merged into one for the final result.
- New facts that contradict old facts should replace them in the final result.
- New and old facts that are unrelated should all be included in the final result.
- Old facts that are not being affected by new facts MUST all be included in the final result.
- Combined facts should be more informative than individual facts
- Maintain factual accuracy while making inferences

### Response Format:
You must follow a **chain of thought** approach in your response:
{{
"reason": Explain your logical inference process and why facts were/weren't combined (1-2 sentences)
"final_result": Return the string of final combining facts
}}

### Example Output:
{{
  "reason": "User wants me to use fewer emojis, so I removed them. Also, the user's name is Hoang, not Thanh, so I corrected that.",
  "final_result": "User's name: Hoang, User's age:23, talk more natural, use less emoji"
}}

### Important Rules:
- The output must be valid JSON format
- Never return explanations or extra characters that surronding the json output, only valid json object that can be used in json.loads()
- Your output must be valid JSON without any markdown code block markers or additional text. Start your response with a curly brace and end with a curly brace.
- NEVER EVER surrounding the output with ```json ```

Input facts:
<OLD_FACTS>{old_facts}</OLD_FACTS>
<NEW_FACTS>{new_facts}</NEW_FACTS>
"""