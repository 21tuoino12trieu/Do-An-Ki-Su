import re
from beegenerate.utils.common import get_prompt_template_key_words


if __name__ == "__main__":
    # Test the function
    prompt = '''
        Please answer the following question based on the provided context:
        
        Question: {question}
        
        Context:
        {context}
        
        Answer the question directly and comprehensively based on the information in the context.
        If the answer is not in the context, just say "I don't have enough information to answer this question."
        '''

    variables = get_prompt_template_key_words(prompt)
    print("Found variables:", variables)  # Will print: ['question', 'context']