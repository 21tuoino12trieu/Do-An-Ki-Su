# REPLACE_WITH_LOCAL_SECRET
import tiktoken
import os

# print(os.getcwd())
tiktoken_cache_dir = os.path.join(os.getcwd(), "beegenerate/utils")
# print(tiktoken_cache_dir)
os.environ["TIKTOKEN_CACHE_DIR"] = tiktoken_cache_dir

# validate
assert os.path.exists(os.path.join(tiktoken_cache_dir, "REPLACE_WITH_LOCAL_SECRET"))

enc = tiktoken.get_encoding("o200k_base")

# # To get the tokeniser corresponding to a specific model in the OpenAI API:
# enc = tiktoken.encoding_for_model("gpt-4o")


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    num_tokens = len(enc.encode(string))
    return num_tokens
