import asyncio

from beememory.constant.ChatConstant import BREAK_LINE


class HandlerResponse:
    @staticmethod
    async def handle_async_final_response(run_function, **kwargs):
        # First, collect all tokens
        full_response = ""
        async for token in run_function(**kwargs):
            try:
                chunk = token.choices[0].delta.content
                if chunk:
                    full_response += chunk
            except:
                pass
            
        safe_kwargs = {k: str(v) for k, v in kwargs.items()}  # Convert values to strings
            
        actual_response_marker = "actual response:"
        marker_pos = full_response.lower().find(actual_response_marker)
        
        
        text_to_process = (
            full_response[marker_pos + len(actual_response_marker):].lstrip()
            if marker_pos != -1
            else full_response
        )
        
        
        responses = [resp.strip() for resp in text_to_process.split(BREAK_LINE)]
        

        for response in responses:
            if response:
                yield response
                await asyncio.sleep(0.5)
        
    @staticmethod
    async def handle_response(run_function, **kwargs):
        # result = await run_function(**kwargs)
        full_response = ""
        async for token in run_function(**kwargs):
            try:
                chunk = token.choices[0].delta.content
                if chunk:
                    full_response += chunk
            except:
                pass
        
        return full_response