from typing import Optional, Dict, Any, Union, List, Tuple
from langfuse import Langfuse
from langfuse.model import BasePromptClient
import inspect
import sys


class BeeLangfuse(Langfuse):
    """
    Enhanced Langfuse client with built-in prompt management capabilities.
    
    Features:
    - All standard Langfuse functionality
    - Advanced prompt management with naming conventions
    - Bulk upload operations
    - Automatic variable name extraction
    
    Naming convention: [project_name]:[prompt_name]
    Example: "BEEACOUNTING:SYSTEM_PROMPT_INTENT"
    """
    
    def __init__(self, **langfuse_kwargs):
        """
        Initialize the enhanced Langfuse client.
        
        Args:
            **langfuse_kwargs: Arguments passed to Langfuse parent class
        """
        # Initialize parent Langfuse class
        super().__init__(**langfuse_kwargs)
    
    def __getitem__(self, prompt_name: str) -> str:
        """
        Get the text content of a prompt by name using bracket notation.
        
        Args:
            prompt_name: The full prompt name in format [project_name]:[prompt_name]
            
        Returns:
            The prompt text content
            
        Raises:
            ValueError: If prompt name doesn't follow naming convention
            Exception: If prompt not found or other Langfuse errors
        """
        try:
            prompt = self.get_prompt(prompt_name)
            return prompt.prompt
            
        except Exception as e:
            raise Exception(f"Failed to retrieve prompt '{prompt_name}': {str(e)}")
    
    def get_prompt_text(self, 
                       prompt_name: str, 
                       version: Optional[int] = None) -> str:
        """
        Get the text content of a prompt by name.
        
        Args:
            prompt_name: The full prompt name in format [project_name]:[prompt_name]
            version: Optional specific version to retrieve (default: latest)
            
        Returns:
            The prompt text content
            
        Raises:
            ValueError: If prompt name doesn't follow naming convention
            Exception: If prompt not found or other Langfuse errors
        """
        if ':' not in prompt_name:
            raise ValueError(
                f"Prompt name '{prompt_name}' must follow format [project_name]:[prompt_name]"
            )
        
        try:
            if version:
                prompt = self.get_prompt(prompt_name, version=version)
            else:
                prompt = self.get_prompt(prompt_name)
            
            return prompt.prompt
            
        except Exception as e:
            raise Exception(f"Failed to retrieve prompt '{prompt_name}': {str(e)}")
    
    def get_prompt_with_metadata(self, prompt_name: str, version: Optional[int] = None) -> Dict[str, Any]:
        """
        Get prompt with full metadata.
        
        Args:
            prompt_name: The full prompt name in format [project_name]:[prompt_name]
            version: Optional specific version to retrieve (default: latest)
            
        Returns:
            Dictionary containing prompt text and metadata
        """
        if ':' not in prompt_name:
            raise ValueError(
                f"Prompt name '{prompt_name}' must follow naming convention [project_name]:[prompt_name]"
            )
        
        try:
            if version:
                prompt = self.get_prompt(prompt_name, version=version)
            else:
                prompt = self.get_prompt(prompt_name)
            
            return {
                'text': prompt.prompt,
                'name': prompt.name,
                'version': prompt.version,
                'config': prompt.config,
                'labels': prompt.labels if hasattr(prompt, 'labels') else [],
                'tags': prompt.tags if hasattr(prompt, 'tags') else []
            }
            
        except Exception as e:
            raise Exception(f"Failed to retrieve prompt '{prompt_name}': {str(e)}")
    
    def format_prompt(self, prompt_name: str, **kwargs) -> str:
        """
        Get and format a prompt with provided variables.
        
        Args:
            prompt_name: The full prompt name in format [project_name]:[prompt_name]
            **kwargs: Variables to format into the prompt
            
        Returns:
            The formatted prompt text
        """
        prompt_text = self.get_prompt_text(prompt_name)
        return prompt_text.format(**kwargs)
    
    def upload_prompts(self,
                       prompt_list: List[str], 
                       chatbot_name: str, 
                       model: str = "beegen-v1",
                       labels: List[str] = None) -> List[Dict[str, Any]]:
        """
        Upload a list of prompts with automatic name extraction.
        
        Args:
            prompt_list: List of prompt variables
            chatbot_name: The chatbot/project name prefix
            model: Model name for config
            labels: Labels for prompts (default: ['production'])
        
        Returns:
            List of upload results
        """
        if labels is None:
            labels = ['production']
        
        # Get the calling frame to access variable names
        frame = inspect.currentframe().f_back
        var_names = frame.f_globals
        
        sample_prompts = []
        
        for prompt_content in prompt_list:
            # Find variable name by matching content
            var_name = None
            for name, value in var_names.items():
                if value is prompt_content and not name.startswith('_'):
                    var_name = name
                    break
            
            if var_name:
                sample_prompts.append({
                    'name': f'{chatbot_name}:{var_name}',
                    'prompt': prompt_content,
                    'config': {'model': model},
                    'labels': labels
                })
        
        results = self.push_prompts(sample_prompts, auto_format_names=False)
        self.print_upload_summary(results)
        return results
    
    def push_prompts(self, prompts_list: List[Dict[str, Any]], 
                     auto_format_names: bool = True,
                     default_project_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Push a list of prompts to Langfuse in bulk.
        
        Args:
            prompts_list: List of dictionaries containing prompt data
            auto_format_names: Whether to automatically format names with project prefix
            default_project_name: Default project name for auto-formatting
            
        Returns:
            List of results with success/error status for each prompt
        """
        results = []
        project_name = default_project_name
        
        for i, prompt_data in enumerate(prompts_list):
            try:
                # Extract required and optional parameters
                name = prompt_data.get('name')
                prompt_content = prompt_data.get('prompt')
                prompt_type = prompt_data.get('type', 'text')  # Default to 'text'
                
                if not name or not prompt_content:
                    results.append({
                        'index': i,
                        'name': name,
                        'status': 'error',
                        'message': 'Missing required fields: name and prompt'
                    })
                    continue
                
                # Auto-format name with project prefix if enabled and not already formatted
                if auto_format_names and ':' not in name:
                    formatted_name = self.create_prompt_name(project_name, name)
                else:
                    formatted_name = name
                
                # Validate naming convention
                if ':' not in formatted_name:
                    results.append({
                        'index': i,
                        'name': name,
                        'status': 'error',
                        'message': 'Prompt name must follow format [project_name]:[prompt_name]'
                    })
                    continue
                
                # Prepare the parameters for create_prompt
                prompt_params = {
                    'name': formatted_name,
                    'prompt': prompt_content,
                    'type': prompt_type
                }
                
                # Add optional parameters if they exist
                if 'labels' in prompt_data:
                    prompt_params['labels'] = prompt_data['labels']
                
                if 'config' in prompt_data:
                    prompt_params['config'] = prompt_data['config']
                
                if 'metadata' in prompt_data:
                    prompt_params['metadata'] = prompt_data['metadata']
                
                if 'tags' in prompt_data:
                    prompt_params['tags'] = prompt_data['tags']
                
                # Create the prompt in Langfuse using parent class method
                response = self.create_prompt(**prompt_params)
                
                results.append({
                    'index': i,
                    'name': formatted_name,
                    'original_name': name,
                    'status': 'success',
                    'prompt_id': response.id if hasattr(response, 'id') else 'created',
                    'version': response.version if hasattr(response, 'version') else 'unknown'
                })
                
            except Exception as e:
                results.append({
                    'index': i,
                    'name': prompt_data.get('name', 'unknown'),
                    'status': 'error',
                    'message': str(e)
                })
        
        return results
    
    def push_simple_prompts(self, 
                           simple_prompts: List[Union[Tuple[str, str], Dict[str, str]]], 
                           auto_format_names: bool = True,
                           default_project_name: Optional[str] = None,
                           default_labels: List[str] = None) -> List[Dict[str, Any]]:
        """
        Push simple prompts (just name and content) to Langfuse.
        
        Args:
            simple_prompts: List of tuples (name, prompt_content) or dict with 'name' and 'prompt' keys
            auto_format_names: Whether to automatically format names with project prefix
            default_project_name: Default project name for auto-formatting
            default_labels: Default labels for all prompts (default: ['production'])
            
        Returns:
            List of results with success/error status for each prompt
        """
        if default_labels is None:
            default_labels = ['production']
            
        formatted_prompts = []
        
        for prompt in simple_prompts:
            if isinstance(prompt, tuple):
                name, content = prompt
                formatted_prompts.append({
                    'name': name,
                    'prompt': content,
                    'type': 'text',
                    'labels': default_labels
                })
            elif isinstance(prompt, dict):
                formatted_prompts.append({
                    'name': prompt['name'],
                    'prompt': prompt['prompt'],
                    'type': prompt.get('type', 'text'),
                    'labels': prompt.get('labels', default_labels),
                    'config': prompt.get('config', {}),
                    'metadata': prompt.get('metadata', {}),
                    'tags': prompt.get('tags', [])
                })
            else:
                raise ValueError(f"Invalid prompt format: {type(prompt)}. Expected tuple or dict.")
        
        return self.push_prompts(formatted_prompts, auto_format_names, default_project_name)
    
    def create_single_prompt(self, 
                           name: str, 
                           prompt_content: str,
                           prompt_type: str = 'text',
                           labels: List[str] = None,
                           config: Dict[str, Any] = None,
                           metadata: Dict[str, Any] = None,
                           tags: List[str] = None,
                           auto_format_name: bool = True,
                           project_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a single prompt in Langfuse.
        
        Args:
            name: Prompt name
            prompt_content: The prompt content
            prompt_type: Type of prompt ('text' or 'chat')
            labels: Labels for the prompt
            config: Configuration dictionary
            metadata: Metadata dictionary
            tags: Tags for the prompt
            auto_format_name: Whether to auto-format with project prefix
            project_name: Project name for formatting (uses project_codename if None)
            
        Returns:
            Result dictionary with success/error status
        """
        if labels is None:
            labels = ['production']
        
        prompt_data = {
            'name': name,
            'prompt': prompt_content,
            'type': prompt_type,
            'labels': labels
        }
        
        if config:
            prompt_data['config'] = config
        if metadata:
            prompt_data['metadata'] = metadata
        if tags:
            prompt_data['tags'] = tags
        
        results = self.push_prompts([prompt_data], auto_format_name, project_name)
        return results[0] if results else {'status': 'error', 'message': 'No result returned'}
    
    def print_upload_summary(self, results: List[Dict[str, Any]]) -> None:
        """
        Print a summary of the upload results.
        
        Args:
            results: List of result dictionaries from push_prompts
        """
        total = len(results)
        successful = len([r for r in results if r['status'] == 'success'])
        failed = total - successful
        
        print(f"\n📊 Prompt Upload Summary:")
        print(f"Total prompts: {total}")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        
        if successful > 0:
            print(f"\n✅ Successfully uploaded:")
            for result in results:
                if result['status'] == 'success':
                    version_info = f" (v{result['version']})" if result.get('version') != 'unknown' else ""
                    print(f"  - {result['name']}{version_info}")
        
        if failed > 0:
            print(f"\n❌ Failed uploads:")
            for result in results:
                if result['status'] == 'error':
                    print(f"  - {result['name']}: {result['message']}")
    
    @classmethod
    def get_instance(cls, project_codename: str = "beegen", **langfuse_kwargs):
        """
        Get the singleton instance for a project_codename.
        
        Args:
            project_codename: The project identifier
            **langfuse_kwargs: Arguments passed to Langfuse parent class
            
        Returns:
            Singleton instance for the given project_codename
        """
        return cls(project_codename, **langfuse_kwargs)
    
    @classmethod
    def clear_instances(cls):
        """
        Clear all singleton instances (useful for testing).
        """
        cls._instances.clear()
    
    @staticmethod
    def create_prompt_name(project_name: str, prompt_name: str) -> str:
        """
        Create a properly formatted prompt name.
        
        Args:
            project_name: The project name
            prompt_name: The prompt name
            
        Returns:
            Formatted prompt name: [project_name]:[prompt_name]
        """
        return f"{project_name}:{prompt_name}"


# Usage examples
if __name__ == "__main__":
    # Initialize with Langfuse connection parameters
    bee_langfuse = BeeLangfuse(
        public_key="pk-lf-93d8aa5d-424b-4e31-96f3-d09fc5b2b24f",
        secret_key="sk-lf-fd1619a2-fd78-4060-b49b-58b0476f1be6",
        host="http://ai-platform-langfuse.tanzu-dev.mbbank.com.vn",
    )
    
    # Use bracket notation to get prompts
    prompt_text = bee_langfuse.get_prompt("BEE247:CEP_MAPPING_PROMPT")
    
    print(prompt_text)