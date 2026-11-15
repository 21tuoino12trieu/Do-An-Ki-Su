from beeflow.configs import NodeConfig
from beegen.const import CONFIG_ROOT
from .base_node import BaseNode
from typing import Dict, Type
import importlib
import json


class NodeFactory:
    r"""Factory class for node creating backends"""
    
    __slots__ = []  # Prevent instance attribute creation
    
    # Initialize with known nodes
    DEFAULT_NODES: Dict[str, str] = {'LLMNodeConfig': 'beeflow.nodes.primitives.ai.llm_node.LLMNode', 'EmbeddingNodeConfig': 'beeflow.nodes.primitives.ai.embedding_node.EmbeddingNode', 'BranchNodeConfig': 'beeflow.nodes.flow.branch_node.BranchNode', 'CodeNodeConfig': 'beeflow.nodes.primitives.transform.code_node.CodeNode', 'ParserNodeConfig': 'beeflow.nodes.primitives.transform.parser_node.ParserNode', 'PromptNodeConfig': 'beeflow.nodes.primitives.transform.prompt_node.PromptNode', 'MilvusNodeConfig': 'beeflow.nodes.primitives.data.milvus_node.MilvusNode', 'MongoNodeConfig': 'beeflow.nodes.primitives.data.mongo_node.MongoNode', 'ForLoopNodeConfig': 'beeflow.nodes.flow.for_loop_node.ForLoopNode', 'GraphNodeConfig': 'beeflow.nodes.graph.graph_node.GraphNode', 'RetrieverNodeConfig': 'beeflow.nodes.templates.retriever_node_v2.RetrieverNode'}
    
    # Custome nodes (loaded from file)
    custom_nodes: Dict[str, str] = {}
    _loaded = False
    
    @classmethod
    def load_custom_registry(cls, filename: str = "custom_nodes.json") -> None:
        """
        Load custom node registry from a JSON file in CONFIG_ROOT.
        If the file doesn't exist, create a new empty JSON file.
        
        Args:
            filename: Name of the JSON file containing custom node mappings
            
        Expected JSON format:
        {
            "CustomNodeConfig1": "path.to.custom.node.CustomNode1",
            "CustomNodeConfig2": "path.to.custom.node.CustomNode2"
        }
        """
        try:
            config_path = CONFIG_ROOT / filename
            
            # Create empty JSON file if it doesn't exist
            if not config_path.exists():
                print(f"Custom registry file not found: {config_path}")
                print(f"Creating empty registry file: {config_path}")
                
                # Ensure the directory exists
                config_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Create empty JSON file
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump({}, f, indent=2)
                
                print(f"Created empty registry file: {config_path}")
                cls._loaded = True
                return
                
            with open(config_path, 'r', encoding='utf-8') as f:
                custom_registry = json.load(f)
                
            if not isinstance(custom_registry, dict):
                raise ValueError("Custom registry must be a dictionary")
                
            # Validate the registry entries
            for config_name, class_path in custom_registry.items():
                if not isinstance(config_name, str) or not isinstance(class_path, str):
                    raise ValueError(f"Invalid registry entry: {config_name} -> {class_path}")
                    
                # Check if class_path looks valid (contains at least one dot)
                if '.' not in class_path:
                    raise ValueError(f"Invalid class path format: {class_path}")
            
            # Update custom nodes registry
            cls.custom_nodes.update(custom_registry)
            cls._loaded = True
            
            print(f"Loaded {len(custom_registry)} custom nodes from {filename}")
            
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON file {filename}: {e}")
        except Exception as e:
            print(f"Error loading custom registry from {filename}: {e}")
    
    @classmethod
    def reload_custom_registry(cls, filename: str = "custom_nodes.json") -> None:
        """
        Reload custom node registry from file, clearing existing custom nodes.
        
        Args:
            filename: Name of the JSON file containing custom node mappings
        """
        cls.custom_nodes.clear()
        cls._loaded = False
        cls.load_custom_registry(filename)
    
    @classmethod
    def get_all_registered_nodes(cls) -> Dict[str, str]:
        """
        Get all registered nodes (default + custom).
        
        Returns:
            Dictionary mapping config class names to node class paths
        """
        if not cls._loaded:
            cls.load_custom_registry()
            
        all_nodes = cls.DEFAULT_NODES.copy()
        all_nodes.update(cls.custom_nodes)
        return all_nodes
    
    @classmethod
    def lazy_import(cls, class_path: str) -> Type[BaseNode]:
        """Lazy import a class from a string path like 'module.submodule.ClassName'"""
        try:
            module_path, class_name = class_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            return getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(f"Failed to import {class_path}: {e}")
    
    @classmethod
    def create(cls, config: NodeConfig) -> BaseNode:
        """Create a node instance based on its type"""
        if not cls._loaded:
            cls.load_custom_registry()
            
        config_class_name = config.__class__.__name__
        
        # Check default nodes first
        if config_class_name in cls.DEFAULT_NODES:
            node_class_path = cls.DEFAULT_NODES[config_class_name]
        # Then check custom nodes
        elif config_class_name in cls.custom_nodes:
            node_class_path = cls.custom_nodes[config_class_name]
        else:
            raise ValueError(f"Unsupported Node Type: {config_class_name}")
        
        # Import and instantiate the node class
        node_class = cls.lazy_import(node_class_path)
        return node_class(config=config)
    
    @classmethod
    def list_available_nodes(cls) -> None:
        """Print all available node types"""
        if not cls._loaded:
            cls.load_custom_registry()
            
        print("Available Node Types:")
        print("\nDefault Nodes:")
        for config_name, class_path in cls.DEFAULT_NODES.items():
            print(f"  {config_name} -> {class_path}")
            
        if cls.custom_nodes:
            print("\nCustom Nodes:")
            for config_name, class_path in cls.custom_nodes.items():
                print(f"  {config_name} -> {class_path}")
        else:
            print("\nNo custom nodes loaded.")

    
    

