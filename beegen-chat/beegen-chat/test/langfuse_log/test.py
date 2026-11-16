import os
import json
import requests
from langfuse import Langfuse
from dotenv import load_dotenv
from langfuse.decorators import observe, langfuse_context

# Khởi tạo Langfuse global - cần thiết cho decorators
load_dotenv()
langfuse = Langfuse(
    secret_key=os.getenv('LANGFUSE_SECRET_KEY'),
    public_key=os.getenv('LANGFUSE_PUBLIC_KEY'),
    host=os.getenv('LANGFUSE_HOST')
)


# os.environ['NO_PROXY'] = '*.mbbank.com.vn'
# langfuse = Langfuse(
#   secret_key="REPLACE_WITH_LOCAL_SECRET",
#   public_key="pk-lf-cfe315c3-2f68-447e-b513-bb80715e73df",
#   host="http://ai-platform-langfuse.tanzu-dev.mbbank.com.vn"
# )

class LLMClient:
    def __init__(self):
        self.url = "http://10.1.87.71:30042/v1/chat/completions"
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer mb123456789',
        }
        self.model = "model/beegen-model-v1"
    
    @observe(as_type="generation")
    def completions(self, prompt: str, temperature: float = 0, top_p: float = 0.1):
        """Send a chat completion request with Langfuse tracing via decorator"""
        
        # Build payload
        messages = [{"role": "user", "content": prompt}]
        payload = {
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
            "frequency_penalty": 0,
            "model": self.model,
            "messages": messages
        }

        # Update langfuse context với input data
        langfuse_context.update_current_observation(
            input=messages,
            model=self.model,
            metadata=payload
        )

        # Gửi request
        response = requests.post(
            self.url, 
            headers=self.headers, 
            json=payload
        )

        # Xử lý response
        if response.status_code == 200:
            response_data = response.json()
            
            # Cập nhật usage statistics cho Langfuse
            input_tokens = response_data["usage"]["prompt_tokens"]
            output_tokens = response_data["usage"]["completion_tokens"]
            total_tokens = response_data["usage"]["total_tokens"]
            
            output_content = response_data["choices"][0]["message"]["content"]
            
            # Update observation trong langfuse_context
            langfuse_context.update_current_observation(
                output=output_content,
                usage_details={
                    "input": input_tokens,
                    "output": output_tokens,
                    "total": total_tokens
                }
            )
            
            return {
                "data": output_content,
                "status_code": response.status_code
            }
        else:
            # Xử lý lỗi và vẫn cập nhật tracing
            langfuse_context.update_current_observation(
                output=None,
                status="error",
                error=f"API Error: {response.status_code}"
            )
            
            return {
                "data": None,
                "status_code": response.status_code,
                "error": response.text
            }

def main():
    """Main function to run the chat API test"""
    try:
        llm_client = LLMClient()
        
        try:
            result = llm_client.completions("xin chào")
            print("API Response Status:", result["status_code"])
            if result["data"]:
                print("Content:", result["data"][:100] + "..." if len(result["data"]) > 100 else result["data"])
            
        except Exception as e:
            print(f"Error in chat completion: {str(e)}")
            
        finally:
            # Đảm bảo flush dữ liệu trong langfuse
            langfuse.flush()
            
    except Exception as e:
        print(f"Error in main: {str(e)}")


if __name__ == "__main__":
    main()