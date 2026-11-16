# Project Documentation

## Module: setup.py


## Module: bee247\bee247_react_bot_v2.py

### Class: Bee247BotV2

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any) -> None
```

#### Method: annotate_query

**Arguments:**
```python
def annotate_query(self: Any, query: Any) -> None
```

#### Method: cep_mapping

**Arguments:**
```python
def cep_mapping(self: Any, query: Any) -> None
```

#### Method: process_tool

**Arguments:**
```python
def process_tool(self: Any, func: Callable) -> str
```

#### Method: create_react_prompt

**Arguments:**
```python
def create_react_prompt(self: Any, question: str) -> str
```


## Module: bee247\card_keyword_extract.py

#### Function: _filter_and_match_keyword

**Arguments:**
```python
def _filter_and_match_keyword(card_keyword_dict: Any, input_list: Any, unique_keywords: Any) -> None
```


## Module: bee247\constants.py


## Module: bee247\semantic_search_bot.py

### Class: SSBot

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, bot_id: str) -> None
```

#### Method: acquire_config

**Arguments:**
```python
def acquire_config(self: Any) -> BotConfig
```


## Module: bee247\topic_classify.py

#### Function: compare_azure_and_qwen

**Arguments:**
```python
def compare_azure_and_qwen() -> None
```


## Module: beeflow\graph.py

### Class: Node

### Class: Graph

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any) -> Any
```


## Module: beeflow\__init__.py


## Module: beeflow\fields\base.py

### Class: DataType

### Class: ValidationRule

### Class: BeeField

**Description:**
Base class for field definitions in nodes


## Module: beeflow\fields\__init__.py


## Module: beeflow\nodes\base.py

### Class: NodeStatus

### Class: ValidationError

**Description:**
Exception raised for validation errors in the workflow system.

This exception should be raised when node inputs, outputs, or state
fail to meet expected requirements.

### Class: State

**Description:**
Maintains the workflow execution state and history.

The State class tracks both the current data state and a historical record
of all state changes during workflow execution.

Attributes:
    data (Dict[str, Any]): Current state data mapping field names to values
    history (List[Dict]): Ordered list of historical state changes

#### Method: update

**Description:**
Updates the current state with new data and records the change in history.

Args:
    node_id (str): Identifier of the node making the update
    data (Dict[str, Any]): New data to merge into the current state
    
The update operation performs a shallow merge of the new data into the
existing state and records the change in the history with a timestamp.

**Arguments:**
```python
def update(self: Any, node_id: str, data: Dict[Any]) -> None
```

#### Method: get

**Description:**
Retrieves a value from the current state by key.

Args:
    key (str): The key to lookup in the state data
    
Returns:
    Any: The value associated with the key
    
Raises:
    KeyError: If the key doesn't exist in the state data

**Arguments:**
```python
def get(self: Any, key: str) -> None
```

### Class: Node

**Description:**
Abstract base class for workflow nodes.

A Node represents a single unit of computation in a workflow. It defines
its required inputs and expected outputs, and implements the computation
logic in the run method.

Attributes:
    node_id (str): Unique identifier for the node
    name (str): Human-readable name for the node
    input_schema (List[Dict]): Set of required input field names
    output_schema (List[Dict]): Set of output field names this node will produce
    status (NodeStatus): Current execution status of the node

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, node_id: str, name: str, input_schema: List[Any], output_schema: List[Any]) -> Any
```

#### Method: execute

**Description:**
Executes the node's computation with the current workflow state.

This method handles the execution lifecycle of the node:
1. Updates node status to RUNNING
2. Gathers required inputs from the state
3. Calls the node's run method with inputs
4. Updates the state with the results

Args:
    state (State): Current workflow state object
    
Raises:
    KeyError: If any required input fields are missing from the state
    ValidationError: If node execution fails validation checks

**Arguments:**
```python
def execute(self: Any, state: State) -> Any
```

#### Method: run

**Description:**
Implements the node's computation logic.

This abstract method must be implemented by concrete node classes to
define their specific computation behavior.

Args:
    inputs (Dict[str, Any]): Dictionary of input values keyed by field name
    
Returns:
    Dict[str, Any]: Dictionary of computed output values keyed by field name
    
Raises:
    ValidationError: If the computation fails or produces invalid results

**Arguments:**
```python
def run(self: Any, inputs: Dict[Any]) -> Dict[Any]
```


## Module: beeflow\nodes\code_node.py


## Module: beeflow\nodes\llm_node.py

### Class: LLMNode

**Description:**
A Node implementation for handling Language Model interactions.

This node processes system and user prompts, validates their required fields,
and formats them with provided inputs to create a sequence of messages for
LLM interaction.

Attributes:
    Inherits all attributes from Node base class.

#### Method: __init__

**Description:**
Initialize the LLMNode.

Args:
    node_id: Unique identifier for the node
    name: Display name of the node
    input_schema: List of required input field names
    output_schema: List of output field names
    system_prompt: Optional system prompt for the LLM
    user_prompt_template: Optional template for formatting user prompts
    **kwargs: Additional keyword arguments passed to parent class

**Arguments:**
```python
def __init__(self: Any, node_id: str, name: str, llm: LLMExecutor, input_schema: List[Any], output_schema: List[Any], system_prompt: Optional[Any], user_prompt: Optional[Any]) -> Any
```


## Module: beeflow\nodes\reranker_node.py


## Module: beeflow\nodes\retrieval_node.py


## Module: beeflow\nodes\router_node.py


## Module: beeflow\nodes\__init__.py


## Module: beegen\const.py

#### Function: get_beegen_root

**Description:**
Get the root directory of installed package.

**Arguments:**
```python
def get_beegen_root() -> None
```


## Module: beegen\__init__.py


## Module: beegen\configs\authen_config.py

### Class: AuthenConfig

**Description:**
Configuration class for authentication settings.

This class inherits from YamlModel and defines the structure for
authentication configuration, particularly for Keycloak integration.

Attributes:
    keycloak_base (str): The base URL for the Keycloak server.
    realm_name (str): The name of the Keycloak realm to be used.
    client_id (str): The client ID for the application in Keycloak.
    client_secret_key (str): The client secret key for the application in Keycloak.
    jwt_secret_key (str): The secret key used for JWT token signing/verification.

Example:
    config = AuthenConfig(
        keycloak_base="https://keycloak.example.com",
        realm_name="my-realm",
        client_id="my-client",
        client_secret_key="secret-key",
        jwt_secret_key="jwt-secret"
    )


## Module: beegen\configs\bot_config.py

### Class: BotConfig

**Description:**
Configuration class for managing bot components and settings.

This class inherits from YamlModel and serves as a central configuration manager
for different components of a bot system, including language models, embeddings,
reranking, and retrieval configurations.

Attributes:
    llm (LLMConfig): Configuration settings for the language model.
    completion (CompletionConfig): Settings for text completion behavior.
    embedding (EmbeddingConfig): Configuration for embedding model and parameters.
    reranking (RerankingConfig): Settings for result reranking functionality.
    retrieval (RetrievalConfig): Configuration for information retrieval system.


## Module: beegen\configs\embedding_config.py

### Class: EmbeddingType

### Class: EmbeddingConfig

**Description:**
Configuration for text embedding services.

This class defines the configuration parameters for various text embedding APIs,
supporting different providers such as OpenAI, Azure, Gemini, and TEI.

Attributes:
    api_type (Optional[EmbeddingType]): The type of embedding API to use.
        Options are defined in the EmbeddingType enum.
        Default is None.
    api_key (Optional[str]): The API key for authenticating with the embedding service.
        Required for OpenAI, Azure, and Gemini. Default is None.
    base_url (Optional[str]): The base URL for the API endpoint.
        Required for Azure and TEI. Default is None.
    api_version (Optional[str]): The version of the API to use, if applicable.
        Required for Azure. Default is None.
    model (Optional[str]): The specific model to use for embedding.
        Required for TEI. Default is None.
    embed_batch_size (Optional[int]): The batch size for embedding requests.
        Default is None.
    dimensions (Optional[int]): The dimensionality of the generated embeddings.
        Required for OpenAI, Azure, and TEI. Default is None.


## Module: beegen\configs\llm_config.py

### Class: LLMType

### Class: CompletionConfig

**Description:**
Configuration for individual LLM completion requests.

This class defines parameters that control the behavior and output of individual
LLM completion requests. It can be used independently or as part of LLMConfig.

Attributes:        
    temperature (float): Higher values make the output more random, while lower values make 
        it focused and deterministic. (default: 0.0)
    top_p (float): An alternative to sampling with temperature, where the model considers the
        results of the tokens with top_p probability mass. top_p = 0.1 means only the tokens
        comprising the top 10% probability mass are considered. (default: 1.0)
    n (int): How many chat completion choices are generated. (default: 1)
    stream (bool): If True, partial message deltas will be sent, like in ChatGPT. This is
        usually much faster for large responses. (default: True)
    stop (Union[str, Sequence[str]]): Up to 4 sequences where the API will stop generating
        further tokens. The returned text will not contain the stop sequence. (default: None)
    max_tokens (int): The maximum number of tokens to generate in the chat completion. 
        The total length of input tokens and generated tokens is limited by the model's context length. (default: None)
    frequency_penalty (float): Number between -2.0 and 2.0. Positive values penalize new tokens
        based on their existing frequency in the text so far, decreasing the model's likelihood
        to repeat the same line verbatim. (default: 0.0)
    presence_penalty (float): Number between -2.0 and 2.0. Positive values penalize new tokens
        based on whether they appear in the text so far, increasing the model's likelihood
        to talk about new topics. (default: 0.0)
    response_format (dict): An object specifying the format that the model must output.
        Setting to { "type": "json_object" } enables JSON mode, which guarantees the message
        the model generates is valid JSON. (default: None)

### Class: LLMConfig

**Description:**
This class defines the configuration parameters for interacting with various LLM APIs,
primarily focused on OpenAI-compatible interfaces.

api_key (str): The API key for authenticating with the LLM service.
    Default is "YOUR_API_KEY", which should be replaced with a valid key.
api_type (LLMType): The type of LLM API to use. 
    Options are defined in the LLMType enum (OPENAI, AZURE, VLLM).
    Default is LLMType.OPENAI.
base_url (str): The base URL for the API endpoint.
    Default is "https://api.openai.com/v1".
api_version (Optional[str]): The version of the API to use, if applicable.
    Default is None.
model (Optional[str]): The specific model to use for inference.
    Default is None. 
 


## Module: beegen\configs\log_config.py

### Class: KafkaLogConfig

**Description:**
Configuration settings for Kafka logging.

This class defines the configuration parameters needed to set up Kafka logging,
including connection details, security settings, and producer configurations.

Attributes:
    kafka_boostrap_servers (List): List of Kafka broker addresses.
    kafka_topic_log (str): The Kafka topic to which logs will be sent.
    kafka_security_protocol (Optional[str]): Security protocol for Kafka connection.
        Defaults to "PLAINTEXT".
    kafka_ssl_ca_file (Optional[str]): Path to SSL CA certificate file.
    kafka_sasl_mechanism (Optional[str]): SASL mechanism for authentication.
    kafka_sasl_username (Optional[str]): SASL username for authentication.
    kafka_sasl_password (Optional[str]): SASL password for authentication.
    kafka_compression_type (Optional[str]): Compression type for messages.
        Options: none, gzip, snappy, lz4. Defaults to 'gzip'.
    kafka_retries (Optional[int]): Number of retry attempts. Defaults to 3.

### Class: StdLogConfig

**Description:**
Configuration settings for standard logging.

This class defines the configuration parameters for standard Python logging,
including file handling, formatting, and additional features.

Attributes:
    log_level (str): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        Defaults to "INFO".
    log_dir (str): Directory where log files will be stored. Defaults to "logs".
    log_filename_prefix (Optional[str]): Prefix for log filenames.
    max_bytes (Optional[int]): Maximum size of each log file in bytes.
        Defaults to 10MB.
    backup_count (Optional[int]): Number of backup files to keep.
        Defaults to 5.
    log_format (Optional[str]): Format string for log messages.

### Class: LogConfig

**Description:**
Main configuration class for logging setup.

This class combines both standard and Kafka logging configurations along with
global settings for the logging system.

Attributes:
    std (StdLogConfig): Standard logging configuration.
    kafka (Optional[KafkaLogConfig]): Kafka logging configuration.
    app_name (str): Name of the application.
    environment (str): Deployment environment (development, staging, production).
    log_filters (Optional[List[str]]): List of modules/loggers to filter out.
    extra_fields (Optional[Dict]): Additional fields to include in log messages.

Raises:
    ValueError: If required fields are missing or invalid environment is specified.


## Module: beegen\configs\milvus_config.py

### Class: MilvusConfig

**Description:**
Configuration settings for Milvus database connection and collections.

A configuration model that handles connection parameters, authentication, and collection settings
for interacting with a Milvus vector database.

Attributes:
    alias (str): Unique identifier for this configuration instance.
    uri (str): Connection URI for the Milvus server.
    username (str): Authentication username.
    password (str): Authentication password.
    db_name (str): Target database name.
    timeout (float, optional): Operation timeout in seconds. Defaults to 10.0.
    connection_pool_size (int, optional): Maximum number of connections in the pool. Defaults to 5.
    enable_ssl (bool, optional): Flag to enable SSL/TLS encryption. Defaults to False.
    ca_path (str, optional): Path to SSL CA certificate file. Required if enable_ssl is True.
    index_params (Dict): Vector index configuration parameters.
    search_params (Dict): Vector search configuration parameters.

Example:
    ```yaml
    milvus_config:
      alias: "prod_db"
      uri: "localhost:19530"
      username: "default"
      password: "password123"
      db_name: "vector_db"
      timeout: 15.0
      index_params:
        metric_type: "L2"
        index_type: "IVF_FLAT"
      search_params:
        nprobe: 10
    ```


## Module: beegen\configs\mongo_config.py

### Class: MongoConfig

**Description:**
Configuration class for MongoDB connection settings, supporting multiple hosts for a cluster.

This class inherits from YamlModel and defines the structure for
MongoDB connection configuration, including a dynamically generated URI for a cluster.

Attributes:
    username (str): The username for authentication with MongoDB.
    password (str): The password for authentication with MongoDB.
    cluster (List[str]): A list of hostnames or IP addresses of the MongoDB cluster nodes.
    authen_source (str): The authentication source (database) for MongoDB.
    readPreference (Optional[str]): The read preference setting for MongoDB operations.
    appname (Optional[str]): The application name for MongoDB monitoring.
    ssl (bool): Whether to use SSL for the connection (default: False).
    directConnection (bool): Whether to use direct connection (default: True).

Properties:
    uri (str): A dynamically generated MongoDB connection URI for the cluster.

Example:
    config = MongoConfig(
        username="myuser",
        password="mypassword",
        cluster=["mongodb1.example.com", "mongodb2.example.com"],
        authen_source="admin",
        readPreference="secondaryPreferred",
        appname="myapp",
        ssl=True,
        directConnection=True
    )
    print(config.uri)  # Outputs the full MongoDB URI with all parameters

#### Method: uri

**Description:**
Generates and returns the MongoDB connection URI for the cluster with all specified parameters.

Returns:
    str: The full MongoDB connection URI including all non-None parameters.

**Arguments:**
```python
def uri(self: Any) -> str
```


## Module: beegen\configs\qa_retrieval_config.py

### Class: QARetrievalConfig

**Description:**
Configuration for information retrieval and reranking processes.

This class defines the parameters used to control the behavior of retrieval
and reranking operations in an information retrieval system.

Attributes:
    retrieval_threshold (Optional[float]): The minimum similarity score for
        initial retrieval results. Documents with scores below this threshold
        will be filtered out. If None, no threshold is applied.

    retrieval_top_k (Optional[int]): The maximum number of documents to
        retrieve in the initial retrieval step. This limits the number of
        results returned by the retrieval process.

    rerank_threshold (Optional[float]): The minimum score for reranked results.
        Documents with reranking scores below this threshold will be filtered out.
        If None, no threshold is applied to reranked results.

    rerank_top_k (Optional[int]): The maximum number of documents to keep
        after reranking. This determines the final number of results returned
        after the reranking process.

Examples:
    Basic configuration:
    ```yaml
    retrieval_top_k: 100
    rerank_top_k: 10
    ```

    Advanced configuration:
    ```yaml
    retrieval_threshold: 0.5
    retrieval_top_k: 200
    rerank_threshold: 0.7
    rerank_top_k: 20
    ```

Note:
    - Setting both threshold and top_k values allows for fine-grained control
      over the retrieval and reranking processes.
    - If a value is set to None, that particular constraint will not be applied.
    - The reranking process typically operates on the results of the initial
      retrieval, so rerank_top_k should generally be less than or equal to
      retrieval_top_k when both are specified.


## Module: beegen\configs\redis_config.py

### Class: RedisConfig

**Description:**
Redis connection configuration.

Defines the connection parameters for Redis instance(s).
Inherits from YamlModel for YAML serialization/deserialization support.

Attributes
----------
host : str
    Redis server hostname or IP address.
    Examples: 'localhost', '127.0.0.1', 'redis.example.com'
port : int
    Redis server port number.
    Default: 6379 (standard Redis port)
    Range: 0-65535


## Module: beegen\configs\reranking_config.py

### Class: RerankingType

### Class: RerankingConfig

**Description:**
Configuration for text reranking services.

This class defines the configuration parameters for text reranking APIs,
which are used to improve the relevance of search results or document rankings.

Attributes:
    api_key (str): The API key for authenticating with the reranking service.
        Default is "YOUR_RERANK_API_KEY". This must be set to a valid API key.

    base_url (Optional[str]): The base URL for the API endpoint.
        Default is None. If not provided, the default URL of the service will be used.

    model (Optional[str]): The specific model to use for reranking.
        Default is None. If not provided, the default model of the service will be used.

The class includes a field validator for the api_key to ensure it's properly set.

Examples:
    Basic configuration:
    ```yaml
    api_key: "your_actual_api_key_here"
    ```

    Advanced configuration:
    ```yaml
    api_key: "your_actual_api_key_here"
    base_url: "https://api.rerank-service.com/v1"
    model: "rerank-v2"
    ```

Note:
    The api_key must be set to a valid key. If it's not set or set to the default value,
    an error will be raised with instructions on how to properly set it in the configuration file.

#### Method: default

**Description:**
Load default config
- Priority: env < default_config_paths
- Inside default_config_paths, the latter one overwrites the former one

**Arguments:**
```python
def default(cls: Any) -> Any
```


## Module: beegen\configs\retrieval_config.py

### Class: RetrievalConfig

**Description:**
Configuration for information retrieval and reranking processes.

This class defines the parameters used to control the behavior of retrieval
and reranking operations in an information retrieval system.

Attributes:
    retrieval_threshold (Optional[float]): The minimum similarity score for
        initial retrieval results. Documents with scores below this threshold
        will be filtered out. If None, no threshold is applied.

    retrieval_top_k (Optional[int]): The maximum number of documents to
        retrieve in the initial retrieval step. This limits the number of
        results returned by the retrieval process.

    rerank_threshold (Optional[float]): The minimum score for reranked results.
        Documents with reranking scores below this threshold will be filtered out.
        If None, no threshold is applied to reranked results.

    rerank_top_k (Optional[int]): The maximum number of documents to keep
        after reranking. This determines the final number of results returned
        after the reranking process.

Examples:
    Basic configuration:
    ```yaml
    retrieval_top_k: 100
    rerank_top_k: 10
    ```

    Advanced configuration:
    ```yaml
    retrieval_threshold: 0.5
    retrieval_top_k: 200
    rerank_threshold: 0.7
    rerank_top_k: 20
    ```

Note:
    - Setting both threshold and top_k values allows for fine-grained control
      over the retrieval and reranking processes.
    - If a value is set to None, that particular constraint will not be applied.
    - The reranking process typically operates on the results of the initial
      retrieval, so rerank_top_k should generally be less than or equal to
      retrieval_top_k when both are specified.


## Module: beegen\configs\server_config.py

### Class: ServerConfig

**Description:**
Configuration class for server settings.

This class inherits from YamlModel and defines the structure for
server configuration, specifying the host and port settings for
the application server.

Attributes:
    host (str): The host address on which the server will listen (e.g., '0.0.0.0', 'localhost').
    port (int): The port number on which the server will accept connections (e.g., 8000).


## Module: beegen\configs\__init__.py


## Module: beegen\embeddings\base.py

### Class: BaseEmbedder

**Description:**
Abstract base class for text embedding functionalities.

#### Method: get_output_dim

**Description:**
Returns the output dimension of the embeddings.

Returns:
    int: The dimensionality of the embeddings for the current model.

**Arguments:**
```python
def get_output_dim(self: Any) -> int
```


## Module: beegen\embeddings\emb_factory.py

### Class: EmbeddingFactory

**Description:**
Factory class for embedding model backends

Raises:
    ValueError: in case the provided model type is unknown.

#### Method: create

**Arguments:**
```python
def create(config: EmbeddingConfig) -> BaseEmbedder
```


## Module: beegen\embeddings\tei_embedding.py

### Class: TEIEmbedding

**Description:**
Text Embedding Inference (TEI) client for generating embeddings via Hugging Face's serving framework.

This class provides an interface to generate text embeddings using TEI servers, which can serve various
embedding models deployed through Hugging Face's Text Embedding Inference framework.

Args:
    config (EmbeddingConfig): Configuration object containing:
        - base_url: URL of the TEI server endpoint
        - api_key: Authentication token for the TEI service
        - api_type: Type of embedding model being served
        - dimensions: Output dimension of the embedding vectors

Example:
    >>> config = EmbeddingConfig(base_url="http://localhost:8080", ...)
    >>> embedder = TEIEmbedding(config)
    >>> embeddings = embedder.embed_list(["text to embed"])

#### Method: __init__

**Description:**
Initialize the TEI embedding client with the provided configuration.

**Arguments:**
```python
def __init__(self: Any, config: EmbeddingConfig) -> Any
```

#### Method: get_output_dim

**Description:**
Get the output dimension of the embeddings.

Returns:
    The dimensionality of the embedding vectors for the current model.

**Arguments:**
```python
def get_output_dim(self: Any) -> int
```

#### Function: cosine_similarity_search

**Description:**
Calculate cosine similarity between a query embedding and a list of embeddings.

Args:
    query_emb (List[float]): Query embedding vector
    embs (List[List[float]]): List of embedding vectors to compare against
    
Returns:
    List[Tuple[int, float]]: List of tuples containing (index, similarity_score)
                            sorted by similarity score in descending order

**Arguments:**
```python
def cosine_similarity_search(query_emb: List[Any], embs: List[Any]) -> List[Any]
```


## Module: beegen\embeddings\__init__.py


## Module: beegen\interpreters\base.py

### Class: BaseInterpreter

**Description:**
An abstract base class for code interpreters.

#### Method: run

**Description:**
Executes the given code based on its type.

Args:
    code (str): The code to be executed.
    code_type (str): The type of the code, which must be one of the
        types returned by `supported_code_types()`.

Returns:
    str: The result of the code execution. If the execution fails, this
        should include sufficient information to diagnose and correct
        the issue.

Raises:
    InterpreterError: If the code execution encounters errors that
        could be resolved by modifying or regenerating the code.

**Arguments:**
```python
def run(self: Any, code: str, code_type: str) -> str
```

#### Method: supported_code_types

**Description:**
Provides supported code types by the interpreter.

**Arguments:**
```python
def supported_code_types(self: Any) -> List[Any]
```

#### Method: update_action_space

**Description:**
Updates action space for *python* interpreter

**Arguments:**
```python
def update_action_space(self: Any, action_space: Dict[Any]) -> Any
```


## Module: beegen\interpreters\internal_python_interpreter.py

### Class: InternalPythonInterpreter

**Description:**
A customized python interpreter to control the execution of
LLM-generated codes. The interpreter makes sure the code can only execute
functions given in action space and import white list. It also supports
fuzzy variable matching to retrieve uncertain input variable name.

.. highlight:: none

This class is adapted from the hugging face implementation
`python_interpreter.py <https://github.com/huggingface/transformers/blob/8f
093fb799246f7dd9104ff44728da0c53a9f67a/src/transformers/tools/python_interp
reter.py>`_. The original license applies::

    Copyright 2023 The HuggingFace Inc. team. All rights reserved.

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
    implied. See the License for the specific language governing
    permissions and limitations under the License.

We have modified the original code to suit our requirements. We have
encapsulated the original functions within a class and saved the
interpreter state after execution. We have added support for "import"
statements, "for" statements, and several binary and unary operators. We
have added import white list to keep `import` statement safe. Additionally,
we have modified the variable matching logic and introduced the
:obj:`fuzz_state` for fuzzy matching.

Modifications copyright (C) 2023 CAMEL-AI.org

Args:
    action_space (Dict[str, Any], optional): A dictionary that maps action
        names to their corresponding functions or objects. The interpreter
        can only execute functions that are either directly listed in this
        dictionary or are member functions of objects listed in this
        dictionary. The concept of :obj:`action_space` is derived from
        EmbodiedAgent, representing the actions that an agent is capable of
        performing. If `None`, set to empty dict. (default: :obj:`None`)
    import_white_list (List[str], optional): A list that stores
        the Python modules or functions that can be imported in the code.
        All submodules and functions of the modules listed in this list are
        importable. Any other import statements will be rejected. The
        module and its submodule or function name are separated by a period
        (:obj:`.`). (default: :obj:`None`)
    unsafe_mode (bool, optional): If `True`, the interpreter runs the code
        by `eval()` without any security check. (default: :obj:`False`)
    raise_error (bool, optional): Raise error if the interpreter fails.
        (default: :obj:`False`)

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, action_space: Optional[Any], import_white_list: Optional[Any], unsafe_mode: bool, raise_error: bool) -> Any
```

#### Method: run

**Description:**
Executes the given code with specified code type in the
interpreter.

This method takes a string of code and its type, checks if the code
type is supported, and then executes the code. If `unsafe_mode` is
set to `False`, the code is executed in a controlled environment using
the `execute` method. If `unsafe_mode` is `True`, the code is executed
using `eval()` with the action space as the global context. An
`InterpreterError` is raised if the code type is unsupported or if any
runtime error occurs during execution.

Args:
    code (str): The python code to be executed.
    code_type (str): The type of the code, which should be one of the
    supported code types (`python`, `py`, `python3`, `python2`).


Returns:
    str: The string representation of the output of the executed code.

Raises:
    InterpreterError: If the `code_type` is not supported or if any
        runtime error occurs during the execution of the code.

**Arguments:**
```python
def run(self: Any, code: str, code_type: str) -> str
```

#### Method: update_action_space

**Description:**
Updates action space for *python* interpreter.

**Arguments:**
```python
def update_action_space(self: Any, action_space: Dict[Any]) -> Any
```

#### Method: supported_code_types

**Description:**
Provides supported code types by the interpreter.

**Arguments:**
```python
def supported_code_types(self: Any) -> List[Any]
```

#### Method: execute

**Description:**
Execute the input python codes in a security environment.

Args:
    code (str): Generated python code to be executed.
    state (Optional[Dict[str, Any]], optional): External variables that
        may be used in the generated code. (default: :obj:`None`)
    fuzz_state (Optional[Dict[str, Any]], optional): External variables
        that do not have certain variable names. The interpreter will
        use fuzzy matching to access these variables. For example, if
        :obj:`fuzz_state` has a variable :obj:`image`, the generated
        code can use :obj:`input_image` to access it. (default:
        :obj:`None`)
    keep_state (bool, optional):  If :obj:`True`, :obj:`state` and
        :obj:`fuzz_state` will be kept for later execution. Otherwise,
        they will be cleared. (default: :obj:`True`)

Returns:
    Any: The value of the last statement (excluding "import") in the
        code. For this interpreter, the value of an expression is its
        value, the value of an "assign" statement is the assigned
        value, and the value of an "if" and "for" block statement is
        the value of the last statement in the block.

**Arguments:**
```python
def execute(self: Any, code: str, state: Optional[Any], fuzz_state: Optional[Any], keep_state: bool) -> Any
```

#### Method: clear_state

**Description:**
Initialize :obj:`state` and :obj:`fuzz_state`.

**Arguments:**
```python
def clear_state(self: Any) -> Any
```

#### Method: _execute_ast

**Arguments:**
```python
def _execute_ast(self: Any, expression: Any) -> Any
```

#### Method: _execute_assign

**Arguments:**
```python
def _execute_assign(self: Any, assign: Any) -> Any
```

#### Method: _assign

**Arguments:**
```python
def _assign(self: Any, target: Any, value: Any) -> None
```

#### Method: _execute_call

**Arguments:**
```python
def _execute_call(self: Any, call: Any) -> Any
```

#### Method: _execute_subscript

**Arguments:**
```python
def _execute_subscript(self: Any, subscript: Any) -> None
```

#### Method: _execute_name

**Arguments:**
```python
def _execute_name(self: Any, name: Any) -> None
```

#### Method: _execute_condition

**Arguments:**
```python
def _execute_condition(self: Any, condition: Any) -> None
```

#### Method: _execute_if

**Arguments:**
```python
def _execute_if(self: Any, if_statement: Any) -> None
```

#### Method: _execute_for

**Arguments:**
```python
def _execute_for(self: Any, for_statement: Any) -> None
```

#### Method: _execute_import

**Arguments:**
```python
def _execute_import(self: Any, import_module: Any) -> Any
```

#### Method: _execute_import_from

**Arguments:**
```python
def _execute_import_from(self: Any, import_from: Any) -> None
```

#### Method: _validate_import

**Arguments:**
```python
def _validate_import(self: Any, full_name: str) -> None
```

#### Method: _execute_binop

**Arguments:**
```python
def _execute_binop(self: Any, binop: Any) -> None
```

#### Method: _execute_unaryop

**Arguments:**
```python
def _execute_unaryop(self: Any, unaryop: Any) -> None
```

#### Method: _get_value_from_state

**Arguments:**
```python
def _get_value_from_state(self: Any, key: str) -> Any
```


## Module: beegen\interpreters\interpreter_error.py

### Class: InterpreterError

**Description:**
Exception raised for errors that can be solved by regenerating code


## Module: beegen\interpreters\subprocess_interpreter.py

### Class: SubprocessInterpreter

**Description:**
SubprocessInterpreter is a class for executing code files or code
strings in a subprocess.

This class handles the execution of code in different scripting languages
(currently Python and Bash) within a subprocess, capturing their
stdout and stderr streams, and allowing user checking before executing code
strings.

Args:
    require_confirm (bool, optional): If True, prompt user before running
        code strings for security. (default: :obj:`True`)
    print_stdout (bool, optional): If True, print the standard output of
        the executed code. (default: :obj:`False`)
    print_stderr (bool, optional): If True, print the standard error of the
        executed code. (default: :obj:`True`)

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, require_confirm: bool, print_stdout: bool, print_stderr: bool) -> Any
```

#### Method: run_file

**Description:**
Executes a code file in a subprocess and captures its output.

Args:
    file (Path): The path object of the file to run.
    code_type (str): The type of code to execute (e.g., 'python',
        'bash').

Returns:
    str: A string containing the captured stdout and stderr of the
        executed code.

Raises:
    RuntimeError: If the provided file path does not point to a file.
    InterpreterError: If the code type provided is not supported.

**Arguments:**
```python
def run_file(self: Any, file: Path, code_type: str) -> str
```

#### Method: run

**Description:**
Generates a temporary file with the given code, executes it, and
    deletes the file afterward.

Args:
    code (str): The code string to execute.
    code_type (str): The type of code to execute (e.g., 'python',
        'bash').

Returns:
    str: A string containing the captured stdout and stderr of the
        executed code.

Raises:
    InterpreterError: If the user declines to run the code or if the
        code type is unsupported.

**Arguments:**
```python
def run(self: Any, code: str, code_type: str) -> str
```

#### Method: _create_temp_file

**Arguments:**
```python
def _create_temp_file(self: Any, code: str, extension: str) -> Path
```

#### Method: _check_code_type

**Arguments:**
```python
def _check_code_type(self: Any, code_type: str) -> str
```

#### Method: supported_code_types

**Description:**
Provides supported code types by the interpreter.

**Arguments:**
```python
def supported_code_types(self: Any) -> List[Any]
```

#### Method: update_action_space

**Description:**
Updates action space for *python* interpreter

**Arguments:**
```python
def update_action_space(self: Any, action_space: Dict[Any]) -> Any
```

#### Function: run_code_string_test

**Arguments:**
```python
def run_code_string_test() -> None
```

#### Function: run_code_file_test

**Arguments:**
```python
def run_code_file_test() -> None
```


## Module: beegen\interpreters\__init__.py


## Module: beegen\llms\llm_executor.py

### Class: LLMExecutor

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, primary_config: LLMConfig, config_store: Optional[Any]) -> Any
```

#### Method: _fallback_config

**Arguments:**
```python
def _fallback_config(self: Any) -> LLMConfig
```


## Module: beegen\llms\llm_response.py

#### Function: chunk_from

**Description:**
Convert a line of response to a ChatCompletionChunk object.

**Arguments:**
```python
def chunk_from(line: str) -> Optional[Any]
```

#### Function: create_error_chunk

**Arguments:**
```python
def create_error_chunk() -> ChatCompletionChunk
```

#### Function: fake_chunk_from

**Arguments:**
```python
def fake_chunk_from(content: str, model: str, chat_id: str, current_time: int, last: Any) -> ChatCompletionChunk
```

#### Function: has_chinese_chars

**Description:**
Check if text contains Chinese characters.

**Arguments:**
```python
def has_chinese_chars(text: str) -> bool
```


## Module: beegen\llms\__init__.py


## Module: beegen\llms\core\azure_model.py

### Class: AzureOpenAIModel

**Description:**
Azure OpenAI API in a unified ModelBackend interface.

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, config: LLMConfig) -> Any
```

#### Method: prepare_request

**Arguments:**
```python
def prepare_request(self: Any, messages: List[Any]) -> Tuple[Any]
```


## Module: beegen\llms\core\base.py

#### Function: set_event_loop_policy

**Arguments:**
```python
def set_event_loop_policy() -> None
```

### Class: HTTPError

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, message: str, status_code: int) -> None
```

### Class: ContentPolicyException

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, message: Any) -> None
```

### Class: BaseLLM

**Description:**
Base class for different model backends. 
May be OpenAI API, a local LLM, a stub for unit tests, etc.

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, config: LLMConfig) -> Any
```

#### Method: prepare_request

**Description:**
Prepare the request URL, headers, and parameters for the API call.

Args:
    messages: List of message dictionaries to be sent to the API
    
Returns:
    Tuple containing:
        - url: The complete API endpoint URL
        - headers: Request headers
        - params: Request parameters

**Arguments:**
```python
def prepare_request(self: Any, messages: List[Any]) -> Tuple[Any]
```


## Module: beegen\llms\core\llm_factory.py

### Class: LLMFactory

**Description:**
Factory class for llm backends.

Raises:
    ValueError: in case the provided model type is unknown.

#### Method: create

**Arguments:**
```python
def create(config: LLMConfig) -> BaseLLM
```


## Module: beegen\llms\core\vllm_model.py

### Class: VllmOpenAIModel

**Description:**
VLLM OpenAI API in a unified ModelBackend interface.

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, config: LLMConfig) -> Any
```

#### Method: prepare_request

**Arguments:**
```python
def prepare_request(self: Any, messages: List[Any]) -> Tuple[Any]
```


## Module: beegen\llms\core\__init__.py


## Module: beegen\logs\loggers.py

#### Function: _setup_console_handler

**Description:**
Setup and configure console handler with UTF-8 encoding

**Arguments:**
```python
def _setup_console_handler(log_level: str, log_format: str) -> Any
```

#### Function: _setup_file_handler

**Description:**
Setup and configure rotating file handler with UTF-8 encoding

**Arguments:**
```python
def _setup_file_handler(log_dir: str, filename_prefix: str, max_bytes: int, backup_count: int, log_level: str, log_format: str) -> Any
```

#### Function: _setup_kafka_handler

**Description:**
Setup and configure Kafka handler

**Arguments:**
```python
def _setup_kafka_handler(kafka_config: Any, std_config: Any, app_config: Any, log_level: str) -> Any
```

#### Function: setup_logger

**Description:**
Setup logger with console, file, and Kafka handlers

**Arguments:**
```python
def setup_logger(config: LogConfig, name: str) -> None
```


## Module: beegen\logs\__init__.py


## Module: beegen\logs\handlers\kafka.py

**Module Description:**
This moudule contains logging handler which forwards logs to Kafka.

### Class: KafkaLoggerException

**Description:**
Exception to identify errors in Kafka Logger.

### Class: KafkaLoggingHandler

**Description:**
This handler enables the user to forward logs to Kafka.

Attributes:
    additional_fields (dict): extra fields attached to logs
    buffer (list): logs (dict) waiting for a flush to Kafka
    buffer_lock (threading.Lock): multithreading lock for a buffet access
    flush_interval (float): scheduled flush interval in seconds
    kafka_topic_name (str): topic name
    main_process_pid (int): pid of the process which initialized logger
    max_buffer_size (int): flush it buffer > max size
    mp_log_handler_flush_lock (threading.Lock):
        locked when mp_log_handler_thread flushes logs
    mp_log_handler_thread (threading.Thread): thread that flushed mp queue
    mp_log_queue (multiprocessing.Queue):
        queue used to redirect logs of child processes
    producer (kafka.KafkaProducer): producer object
    timer (threading.Timer): thread with a scheduled logs flush
    unhandled_exception_logger (logging.Logger):
        logger that will be used to log unhandled top-level exception

#### Method: __init__

**Description:**
Initialize the handler.

Args:
    hosts_list: list of the Kafka hostnames
    topic: kafka consumer topic to where logs are forwarded
    security_protocol (str, optional): KafkaProducer security protocol
    ssl_cafile (None, optional): path to CA file
    kafka_producer_args (None, optional):
        extra arguments to pass to KafkaProducer
    kafka_producer_init_retries (int, optional):
        number of addtional attempts to initialize Kafka producer
    kafka_producer_init_delay_ms (int, optional):
        static delay for attempts to initialize Kafka producer
    kafka_producer_init_delay_rand_ms (int, optional):
        randomized delay for attempts to initialize Kafka producer
    additional_fields (None, optional):
        A dictionary with all the additional fields that you would like to add to the logs, such the
        application, environment, etc.
    flush_buffer_size (None/int, optional):
        flush if buffer > max size, None means there is no restriction
    flush_interval (int, optional): scheduled flush interval in seconds
    unhandled_exception_logger (None/logging.Logger, optional):
        loger that will be used to log unhandled top-level exception
    log_preprocess (None/list, optional):
        list of functions, handler will send the following to Kafka
        ...preprocess[1](preprocess[0](raw_log))...

Raises:
    KafkaLoggerException: in case of incorrect logger configuration

**Arguments:**
```python
def __init__(self: Any, hosts_list: Any, topic: Any, security_protocol: Any, ssl_cafile: Any, kafka_producer_args: Any, kafka_producer_init_retries: Any, kafka_producer_init_delay_ms: Any, kafka_producer_init_delay_rand_ms: Any, additional_fields: Any, flush_buffer_size: Any, flush_interval: Any, unhandled_exception_logger: Any, log_preprocess: Any) -> None
```

#### Method: prepare_record_dict

**Description:**
Prepare a dictionary log item.
Format a log record and extend dictionary with default values.

Args:
    record (logging.LogRecord): log record

Returns:
    dict: log item ready for Kafka

**Arguments:**
```python
def prepare_record_dict(self: Any, record: Any) -> None
```

#### Method: emit

**Description:**
Add log to the buffer or forward to the main process.

Args:
    record: Logging message

**Arguments:**
```python
def emit(self: Any, record: Any) -> None
```

#### Method: append_to_buffer

**Description:**
Place log dictionary to the buffer.
Triggers/schedules a flush of the buffer.

Args:
    record_dict (dict): log item

**Arguments:**
```python
def append_to_buffer(self: Any, record_dict: Any) -> None
```

#### Method: flush

**Description:**
Flush a buffer to Kafka.
Skip if the buffer is empty.
Use multithreading lock to access buffer.

**Arguments:**
```python
def flush(self: Any) -> None
```

#### Method: schedule_flush

**Description:**
Run a daemon thread that will flush buffer.

**Arguments:**
```python
def schedule_flush(self: Any) -> None
```

#### Method: mp_log_handler

**Description:**
Emit logs from multiprocessing queue.

**Arguments:**
```python
def mp_log_handler(self: Any) -> None
```

#### Method: at_exit

**Description:**
Flush logs at exit, close the producer.
Flush operation will close scheduled flush thread.
Kafka raise RecordAccumulator in case of flushing in close method.

**Arguments:**
```python
def at_exit(self: Any) -> None
```

#### Method: unhandled_exception

**Description:**
Log top-level exception to the provided logger.

Args:
    exctype (type): type of the exception
    exception (Exception): exception object from excepthook
    traceback (traceback): traceback object

**Arguments:**
```python
def unhandled_exception(self: Any, exctype: Any, exception: Any, traceback: Any) -> None
```

#### Method: close

**Description:**
Close the handler.

**Arguments:**
```python
def close(self: Any) -> None
```


## Module: beegen\logs\handlers\__init__.py


## Module: beegen\prompts\base.py

#### Function: return_prompt_wrapper

**Description:**
Wrapper that converts the return value of a function to an input
class instance if it's a string.

Args:
    cls (Any): The class to convert to.
    func (Callable): The function to decorate.

Returns:
    Callable[..., Union[Any, str]]: Decorated function that
        returns the decorated class instance if the return value is a
        string.

**Arguments:**
```python
def return_prompt_wrapper(cls: Any, func: Callable) -> Callable[Any]
```

#### Function: wrap_prompt_functions

**Description:**
Decorator that wraps functions of a class inherited from :obj:`str`
with the :obj:`return_text_prompt` decorator.

Args:
    cls (type): The class to decorate.

Returns:
    type: Decorated class with wrapped functions.

**Arguments:**
```python
def wrap_prompt_functions(cls: T) -> T
```

### Class: TextPrompt

**Description:**
A class that represents a text prompt. The :obj:`TextPrompt` class
extends the built-in :obj:`str` class to provide a property for retrieving
the set of keywords in the prompt.

Attributes:
    key_words (set): A set of strings representing the keywords in the
        prompt.

#### Method: key_words

**Description:**
Return a set of strings representing the keywords in the prompt.

**Arguments:**
```python
def key_words(self: Any) -> Set[Any]
```

#### Method: format

**Description:**
Overrides the built-in :obj:`str.format` method to allow for
default values in the format string. This is used to allow formatting
the partial string.

Args:
    *args (Any): Variable length argument list.
    **kwargs (Any): Arbitrary keyword arguments.

Returns:
    TextPrompt: A new :obj:`TextPrompt` object with the format string
        replaced with the formatted string.

**Arguments:**
```python
def format(self: Any) -> Any
```

### Class: CodePrompt

**Description:**
A class that represents a code prompt. It extends the :obj:`TextPrompt`
class with a :obj:`code_type` property.

Attributes:
    code_type (str, optional): The type of code. Defaults to None.

#### Method: __new__

**Description:**
Creates a new instance of the :obj:`CodePrompt` class.

Args:
    *args (Any): Positional arguments.
    **kwargs (Any): Keyword arguments.

Returns:
    CodePrompt: The created :obj:`CodePrompt` instance.

**Arguments:**
```python
def __new__(cls: Any) -> Any
```

#### Method: code_type

**Description:**
Returns the type of code.

Returns:
    Optional[str]: The type of code.

**Arguments:**
```python
def code_type(self: Any) -> Optional[Any]
```

#### Method: set_code_type

**Description:**
Sets the type of code.

Args:
    code_type (str): The type of code.

**Arguments:**
```python
def set_code_type(self: Any, code_type: str) -> Any
```

#### Method: execute

**Description:**
Executes the code string using the provided interpreter.

This method runs a code string through either a specified interpreter
or a default one. It supports additional keyword arguments for
flexibility.

Args:
    interpreter (Optional[BaseInterpreter]): The interpreter instance
        to use for execution. If `None`, a default interpreter is used.
        (default: :obj:`None`)
    **kwargs: Additional keyword arguments passed to the interpreter to
        run the code.

Returns:
    str: The result of the code execution. If the execution fails, this
        should include sufficient information to diagnose and correct
        the issue.

Raises:
    InterpreterError: If the code execution encounters errors that
        could be resolved by modifying or regenerating the code.

**Arguments:**
```python
def execute(self: Any, interpreter: Optional[Any]) -> str
```


## Module: beegen\prompts\bee247.py


## Module: beegen\prompts\bee247_v2.py


## Module: beegen\prompts\beegen_common.py


## Module: beegen\prompts\happy_hub.py


## Module: beegen\prompts\semantic_search.py


## Module: beegen\prompts\semantic_search_v2.py


## Module: beegen\prompts\__init__.py


## Module: beegen\reranks\base.py

### Class: BaseReranker

**Description:**
Abstract base class for reranking functionalities.


## Module: beegen\reranks\rerank_factory.py

### Class: RerankingFactory

**Description:**
Factory class for reranking model backends

Raises:
    ValueError: in case the provided model type is unknown.

#### Method: create

**Arguments:**
```python
def create(config: RerankingConfig) -> BaseReranker
```


## Module: beegen\reranks\tei_reranker.py

### Class: TEIReranker

**Description:**
Provides text reranking functionalities using Text Embedding Inference.

#### Method: __init__

**Description:**
Initialize the TEI embedding client with the provided configuration.

**Arguments:**
```python
def __init__(self: Any, config: RerankingConfig) -> Any
```


## Module: beegen\reranks\__init__.py


## Module: beegen\retrievers\base.py

### Class: BaseRetriever

**Description:**
Abstract base class for implementing various types of information retrievers.


## Module: beegen\retrievers\hybrid_retriever.py

### Class: HybridRetriever

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, storage: BaseVectorStore, embedding: BaseEmbedder, bm25search: BM25Search, reranker: Optional[Any]) -> None
```


## Module: beegen\retrievers\vector_retriever.py

### Class: VectorRetriever

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, storage: BaseVectorStore, embedding: BaseEmbedder, reranker: Optional[Any]) -> None
```


## Module: beegen\retrievers\vector_retriever_v2.py

### Class: VectorRetriever

**Description:**
Retrieves documents using vector similarity search.

Combines vector embeddings, vector storage, and document storage to perform
semantic similarity search and return matching documents.

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, embedder: BaseEmbedder, vec_store: BaseVectorStore, doc_store: DocumentStore) -> Any
```


## Module: beegen\retrievers\__init__.py


## Module: beegen\searchs\bm25_search.py

### Class: BM25Search

**Description:**
Use BM25 to search similarity documents

Args:
    corpus (List[dict]): BM25 use corpus to create vocab
    path_stopword (str): List stopword of Vietnamese
    lowercase (Bool): if true, lower text before tokenzer

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, corpus: List[Any], path_stopword: str, lowercase: bool) -> Any
```

#### Method: _get_corpus_text

**Arguments:**
```python
def _get_corpus_text(self: Any) -> None
```

#### Method: _create_model_bm25

**Arguments:**
```python
def _create_model_bm25(self: Any) -> None
```

#### Method: save_model_bm25

**Arguments:**
```python
def save_model_bm25(self: Any, path: Any) -> Any
```

#### Method: load_model_bm25

**Arguments:**
```python
def load_model_bm25(self: Any, path: Any, load_corpus: Any) -> Any
```

#### Method: _search

**Description:**
Search documents similar to the query

Args:
    query (str): question of user
    top_k (int): number of potential documents returned

Return:
    List[str]: List of chunk ids

**Arguments:**
```python
def _search(self: Any, query: str, top_k: int) -> None
```


## Module: beegen\storage\__init__.py


## Module: beegen\storage\mongo\bot_store.py

### Class: BotStore

**Description:**
A class for managing bot configurations using MongoDB as the storage backend.

This class provides functionality to store, retrieve, and manage bot configurations
including their LLM settings, embedding parameters, reranking configurations,
and retrieval settings.

Attributes:
    config (Optional[MongoConfig]): MongoDB configuration settings

#### Method: __init__

**Description:**
Initialize the BotStore instance.

Args:
    config (Optional[MongoConfig]): Configuration for MongoDB connection.
        If None, default configuration will be used.

**Arguments:**
```python
def __init__(self: Any, config: Optional[Any]) -> Any
```

#### Method: fetch_active_bots

**Description:**
Retrieve and process configurations for all available bots.

This method fetches all bot records from the database that have metadata
and attempts to load their configurations. Failed configurations are logged
but don't prevent other configurations from being loaded.

Returns:
    Dict[str, Dict[str, Any]]: A dictionary mapping bot IDs to their 
        respective configurations.

Example:
    >>> bot_store = BotStore()
    >>> configs = bot_store.get_all_bot_configs()
    >>> print(configs['bot_id']['llm'].base_url)

**Arguments:**
```python
def fetch_active_bots(self: Any) -> Dict[Any]
```

#### Method: fetch_bot_details

**Description:**
Retrieve and process bot-specific configuration from MongoDB.

This method fetches configuration parameters including LLM configuration,
embedding generation settings, reranking parameters, document retrieval
settings, and bot definition/system prompt.

Args:
    bot_id (str): The unique identifier for the bot whose configuration
        should be retrieved.

Returns:
    Dict[str, Any]: A dictionary containing processed configuration settings
        with the following keys:
        - id: bot identifier
        - llm: LLM configuration
        - embedding: embedding generation settings
        - reranking: reranking parameters
        - retrieval: document retrieval settings
        - definition: bot system prompt

Raises:
    ValueError: If the specified bot doesn't exist or is not configured.

Example:
    >>> bot_store = BotStore()
    >>> config = bot_store.acquire_config('my_bot_id')
    >>> print(config['llm'].base_url)

**Arguments:**
```python
def fetch_bot_details(self: Any, bot_id: str) -> Dict[Any]
```


## Module: beegen\storage\mongo\document_store.py

### Class: DocumentStore

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, config: Optional[Any]) -> Any
```

#### Method: find_document_chunks

**Description:**
Retrieves document chunks and their metadata from MongoDB based on Milvus chunk IDs.

Args:
    chunk_ids: List of chunk identifiers from Milvus.

Returns:
    A dictionary mapping chunk IDs to their corresponding content and metadata.

**Arguments:**
```python
def find_document_chunks(self: Any, chunk_ids: List[Any], collection_name: str) -> List[Any]
```

#### Function: main

**Arguments:**
```python
def main() -> None
```


## Module: beegen\storage\mongo\mongodb.py

### Class: MongoStorage

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, config: Optional[Any]) -> None
```

#### Method: from_path

**Description:**
Create a MongoStorage instance from a config file path.

Args:
    path: Path to the mongo config YAML file
    
Returns:
    MongoStorage: A new instance initialized with the config

**Arguments:**
```python
def from_path(cls: Any, path: Union[Any]) -> Any
```

#### Method: connect

**Arguments:**
```python
def connect(self: Any) -> None
```

#### Method: disconnect

**Arguments:**
```python
def disconnect(self: Any) -> None
```

#### Method: db

**Arguments:**
```python
def db(self: Any) -> Database
```

#### Method: find

**Description:**
Excute a MongoDB query and return results as dictionary/dictionaries

Args:
    collection_name (str): name of the collection to query
    query (dict): MongoDB query to execute

Returns:
    List[Dict]: query results

**Arguments:**
```python
def find(self: Any, collection_name: str, query: Dict) -> List[Any]
```

#### Method: insert

**Description:**
Insert a single document into a MongoDB collection

Args:
    collection_name (str): name of the collection to insert into
    document (Dict): document to insert
    
Returns:
    bool: True if insertion was successful
    
Raises:
    ConnectionError: if database is not connected
    Exception: if insertion fails for any other reason

**Arguments:**
```python
def insert(self: Any, collection_name: str, document: Dict) -> bool
```

#### Function: main

**Arguments:**
```python
def main() -> None
```

#### Function: single_request

**Description:**
Execute a single request to MongoDB

**Arguments:**
```python
def single_request(mongodb: MongoStorage, request_id: int) -> List[Any]
```

#### Function: execute_request

**Description:**
Execute a single request and update global counters

**Arguments:**
```python
def execute_request(mongodb: MongoStorage, request_id: int) -> None
```

#### Function: test_ccu

**Description:**
Test Concurrent User (CCU) handling by sending multiple concurrent requests

Args:
    num_requests (int): Number of concurrent requests to simulate

**Arguments:**
```python
def test_ccu(num_requests: int) -> None
```


## Module: beegen\storage\mongo\__init__.py


## Module: beegen\tools\bee247_tools.py

#### Function: card_retrieval

**Description:**
Retrieves relevant card documents based on semantic search for RAG-based generation.

This function performs semantic search against a collection of card-related documents,
filtering by both the search query and specified topics.

Args:
    query (str): The short search-optimized query in Vietnamese, refined from the user's question.
    topics (List[str]): all topics that are semantically related to the query.
        Topics MUST be from the predefined list below AND must have semantic relevance to the query intent. For example:
        [    
            "Dịch vụ trả góp qua thẻ tín dụng",
            "Dịch vụ thanh toán thẻ qua Ví Apple Pay",
            "Dịch vụ thanh toán giao dịch quảng cáo bằng thẻ",
            "Thẻ tín dụng quốc tế JCB Credit",
            "Thẻ tín dụng Visa Priority",
            "Thẻ tín dụng Visa Credit",
            "Thẻ tín dụng JCB Ultimate",
            "Thẻ đa năng Hi Slay-dy Mastercard",
            "Thẻ đa năng JCB Hi Collection",
            "Thẻ đa năng JCB Hi Sky",
            "Thẻ đa năng Mastercard Hi Green",
            "Thẻ đa năng Led-Visa Hi Collection",
            "Thẻ đa năng Master Hi League Of Legends (Hi LOL)",
            "Thẻ đa năng - Vòng tay thanh toán Stellar",
            "Thẻ đa năng Visa Hybrid",
            "Thẻ ghi nợ quốc tế Unionpay",
            "Thẻ ghi nợ nội địa Active Plus",
            "Thẻ ghi nợ Visa Debit",
            "Thẻ liên kết MB - Hi Shopee Food (JCB)"
        ]

Returns:
    List: Retrieved card documents matching the query and selected topics.

**Arguments:**
```python
def card_retrieval(query: str, topics: List[Any]) -> List
```

#### Function: common_retrieval

**Description:**
Performs semantic search over general banking documents and customer resources.

Serves as a fallback retrieval method when card_retrieval() is not applicable.
Searches across these categories:
    - Định danh (Identity Verification Guides)
    - Thẻ (Cards)
    - Ngân hàng điện tử (Digital Banking)
    - Top các nhu cầu của khách hàng (Top Customer Needs)
    - Vay online (Online Loans)

Args:
    query (str): Search query (refined from user question, in Vietnamese) to match against the document collection.

Returns:
    List: Retrieved documents matching the query.

**Arguments:**
```python
def common_retrieval(query: str) -> List
```

#### Function: general_chat

**Description:**
Handles casual conversations and non-banking related queries.

This function provides appropriate responses for:
    - Greetings and farewells
    - Small talk
    - Personal questions
    - Emotional expressions
    - General questions not related to banking services

Args:
    query (str): The user's conversational input in Vietnamese.

**Arguments:**
```python
def general_chat(query: str) -> Dict[Any]
```


## Module: beegen\tools\function_tool.py

#### Function: _remove_a_key

**Description:**
Remove a key from a dictionary recursively.

**Arguments:**
```python
def _remove_a_key(d: Dict, remove_key: Any) -> Any
```

#### Function: get_openai_function_schema

**Description:**
Generates a schema dict for an OpenAI function based on its signature.

This function is deprecated and will be replaced by
:obj:`get_openai_tool_schema()` in future versions. It parses the
function's parameters and docstring to construct a JSON schema-like
dictionary.

Args:
    func (Callable): The OpenAI function to generate the schema for.

Returns:
    Dict[str, Any]: A dictionary representing the JSON schema of the
        function, including its name, description, and parameter
        specifications.

**Arguments:**
```python
def get_openai_function_schema(func: Callable) -> Dict[Any]
```

#### Function: get_openai_tool_schema

**Description:**
Generates an OpenAI JSON schema from a given Python function.

This function creates a schema compatible with OpenAI's API specifications,
based on the provided Python function. It processes the function's
parameters, types, and docstrings, and constructs a schema accordingly.

Note:
    - Each parameter in `func` must have a type annotation; otherwise, it's
      treated as 'Any'.
    - Variable arguments (*args) and keyword arguments (**kwargs) are not
      supported and will be ignored.
    - A functional description including a brief and detailed explanation
      should be provided in the docstring of `func`.
    - All parameters of `func` must be described in its docstring.
    - Supported docstring styles: ReST, Google, Numpydoc, and Epydoc.

Args:
    func (Callable): The Python function to be converted into an OpenAI
                     JSON schema.

Returns:
    Dict[str, Any]: A dictionary representing the OpenAI JSON schema of
                    the provided function.

See Also:
    `OpenAI API Reference
        <https://platform.openai.com/docs/api-reference/assistants/object>`_

**Arguments:**
```python
def get_openai_tool_schema(func: Callable) -> Dict[Any]
```

### Class: FunctionTool

**Description:**
An abstraction of a function that OpenAI chat models can call. See
https://platform.openai.com/docs/api-reference/chat/create.

By default, the tool schema will be parsed from the func, or you can
provide a user-defined tool schema to override.

Args:
    func (Callable): The function to call.The tool schema is parsed from
        the signature and docstring by default.
    openai_tool_schema (Optional[Dict[str, Any]], optional): A user-defined
        openai tool schema to override the default result.
        (default: :obj:`None`)

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, func: Callable, openai_tool_schema: Optional[Any]) -> Any
```

#### Method: validate_openai_tool_schema

**Description:**
Validates the OpenAI tool schema against
:obj:`ToolAssistantToolsFunction`.
This function checks if the provided :obj:`openai_tool_schema` adheres
to the specifications required by OpenAI's
:obj:`ToolAssistantToolsFunction`. It ensures that the function
description and parameters are correctly formatted according to JSON
Schema specifications.
Args:
    openai_tool_schema (Dict[str, Any]): The OpenAI tool schema to
        validate.
Raises:
    ValidationError: If the schema does not comply with the
        specifications.
    SchemaError: If the parameters do not meet JSON Schema reference
        specifications.

**Arguments:**
```python
def validate_openai_tool_schema(openai_tool_schema: Dict[Any]) -> Any
```

#### Method: get_openai_tool_schema

**Description:**
Gets the OpenAI tool schema for this function.

This method returns the OpenAI tool schema associated with this
function, after validating it to ensure it meets OpenAI's
specifications.

Returns:
    Dict[str, Any]: The OpenAI tool schema for this function.

**Arguments:**
```python
def get_openai_tool_schema(self: Any) -> Dict[Any]
```

#### Method: set_openai_tool_schema

**Description:**
Sets the OpenAI tool schema for this function.

Allows setting a custom OpenAI tool schema for this function.

Args:
    schema (Dict[str, Any]): The OpenAI tool schema to set.

**Arguments:**
```python
def set_openai_tool_schema(self: Any, schema: Dict[Any]) -> Any
```

#### Method: get_openai_function_schema

**Description:**
Gets the schema of the function from the OpenAI tool schema.

This method extracts and returns the function-specific part of the
OpenAI tool schema associated with this function.

Returns:
    Dict[str, Any]: The schema of the function within the OpenAI tool
        schema.

**Arguments:**
```python
def get_openai_function_schema(self: Any) -> Dict[Any]
```

#### Method: set_openai_function_schema

**Description:**
Sets the schema of the function within the OpenAI tool schema.

Args:
    openai_function_schema (Dict[str, Any]): The function schema to set
        within the OpenAI tool schema.

**Arguments:**
```python
def set_openai_function_schema(self: Any, openai_function_schema: Dict[Any]) -> Any
```

#### Method: get_function_name

**Description:**
Gets the name of the function from the OpenAI tool schema.

Returns:
    str: The name of the function.

**Arguments:**
```python
def get_function_name(self: Any) -> str
```

#### Method: set_function_name

**Description:**
Sets the name of the function in the OpenAI tool schema.

Args:
    name (str): The name of the function to set.

**Arguments:**
```python
def set_function_name(self: Any, name: str) -> Any
```

#### Method: get_function_description

**Description:**
Gets the description of the function from the OpenAI tool
schema.

Returns:
    str: The description of the function.

**Arguments:**
```python
def get_function_description(self: Any) -> str
```

#### Method: set_function_description

**Description:**
Sets the description of the function in the OpenAI tool schema.

Args:
    description (str): The description for the function.

**Arguments:**
```python
def set_function_description(self: Any, description: str) -> Any
```

#### Method: get_paramter_description

**Description:**
Gets the description of a specific parameter from the function
schema.

Args:
    param_name (str): The name of the parameter to get the
        description.

Returns:
    str: The description of the specified parameter.

**Arguments:**
```python
def get_paramter_description(self: Any, param_name: str) -> str
```

#### Method: set_paramter_description

**Description:**
Sets the description for a specific parameter in the function
schema.

Args:
    param_name (str): The name of the parameter to set the description
        for.
    description (str): The description for the parameter.

**Arguments:**
```python
def set_paramter_description(self: Any, param_name: str, description: str) -> Any
```

#### Method: get_parameter

**Description:**
Gets the schema for a specific parameter from the function schema.

Args:
    param_name (str): The name of the parameter to get the schema.

Returns:
    Dict[str, Any]: The schema of the specified parameter.

**Arguments:**
```python
def get_parameter(self: Any, param_name: str) -> Dict[Any]
```

#### Method: set_parameter

**Description:**
Sets the schema for a specific parameter in the function schema.

Args:
    param_name (str): The name of the parameter to set the schema for.
    value (Dict[str, Any]): The schema to set for the parameter.

**Arguments:**
```python
def set_parameter(self: Any, param_name: str, value: Dict[Any]) -> None
```

#### Method: parameters

**Description:**
Getter method for the property :obj:`parameters`.

Returns:
    Dict[str, Any]: the dictionary containing information of
        parameters of this function.

**Arguments:**
```python
def parameters(self: Any) -> Dict[Any]
```

#### Method: parameters

**Description:**
Setter method for the property :obj:`parameters`. It will
firstly check if the input parameters schema is valid. If invalid,
the method will raise :obj:`jsonschema.exceptions.SchemaError`.

Args:
    value (Dict[str, Any]): the new dictionary value for the
        function's parameters.

**Arguments:**
```python
def parameters(self: Any, value: Dict[Any]) -> Any
```

### Class: OpenAIFunction

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any) -> None
```


## Module: beegen\tools\__init__.py


## Module: beegen\utils\async_func.py

#### Function: to_async_funcs

**Description:**
Convert a list of Python synchronous functions to Python
asynchronous functions.

Args:
    funcs (list[FunctionTool]): List of Python synchronous
        functions in the :obj:`FunctionTool` format.

Returns:
    list[FunctionTool]: List of Python asynchronous functions
        in the :obj:`FunctionTool` format.

**Arguments:**
```python
def to_async_funcs(funcs: list[Any]) -> list[Any]
```


## Module: beegen\utils\common.py

#### Function: to_pascal

**Description:**
Convert a snake_case string to PascalCase.

Args:
    snake (str): The snake_case string to be converted.

Returns:
    str: The converted PascalCase string.

**Arguments:**
```python
def to_pascal(snake: str) -> str
```

#### Function: configure_event_loop

**Description:**
Configure the event loop policy based on the operating system.

Raises:
    RuntimeError: If the platform is not supported.

**Arguments:**
```python
def configure_event_loop() -> Any
```

#### Function: raise_error

**Description:**
Logs and raises the provided exception.

Args:
    e (Exception): Exception to be logged and raised
    
Raises:
    The provided exception

**Arguments:**
```python
def raise_error(e: Exception) -> None
```

#### Function: get_system_information

**Description:**
Gathers information about the operating system.

Returns:
    dict: A dictionary containing various pieces of OS information.

**Arguments:**
```python
def get_system_information() -> None
```

#### Function: get_prompt_template_key_words

**Description:**
Given a string template containing curly braces {}, return a set of
the words inside the braces.

Args:
    template (str): A string containing curly braces.

Returns:
    List[str]: A list of the words inside the curly braces.

Example:
    >>> get_prompt_template_key_words('Hi, {name}! How are you {status}?')
    {'name', 'status'}

**Arguments:**
```python
def get_prompt_template_key_words(template: str) -> Set[Any]
```

#### Function: join_dicts

**Description:**
Join two lists of dictionaries based on a common key, similar to LEFT JOIN in SQL.

Args:
    source_data (List[dict]): Primary data list that will be enriched
    lookup_data (List[dict]): Secondary data list used for enrichment
    join_key (str): Key used to match records between the two lists. Defaults to 'id'
    
Returns:
    List[dict]: Merged records from both lists, maintaining source_data order and keeping all 
               source_data records even if no match exists in lookup_data

Example:
    >>> content_data = [{'id': '123', 'text': 'abc'}] 
    >>> metadata = [{'id': '123', 'score': 0.9}]
    >>> join_dicts(content_data, metadata)
    [{'id': '123', 'text': 'abc', 'score': 0.9}]

**Arguments:**
```python
def join_dicts(source_data: List[Any], lookup_data: List[Any], join_key: str) -> List[Any]
```

#### Function: transform_bot_id

**Arguments:**
```python
def transform_bot_id(bot_id: str) -> str
```


## Module: beegen\utils\cost_manager.py

### Class: Costs

### Class: CostManager

**Description:**
Calculate the overhead of using the iterface

#### Method: update_cost

**Description:**
Update the total cost, prompt tokens, and completion tokens.

Args:
prompt_tokens (int): The number of tokens used in the prompt.
completion_tokens (int): The number of tokens used in the completion.
model (str): The model used for the API call.

**Arguments:**
```python
def update_cost(self: Any, prompt_tokens: Any, completion_tokens: Any, model: Any) -> None
```

#### Method: get_costs

**Description:**
Get all costs

**Arguments:**
```python
def get_costs(self: Any) -> Costs
```

### Class: TokenCostManager

**Description:**
open llm model is self-host, it's free and without cost

#### Method: update_cost

**Description:**
Update the total cost, prompt tokens, and completion tokens.

Args:
prompt_tokens (int): The number of tokens used in the prompt.
completion_tokens (int): The number of tokens used in the completion.
model (str): The model used for the API call.

**Arguments:**
```python
def update_cost(self: Any, prompt_tokens: Any, completion_tokens: Any, model: Any) -> None
```


## Module: beegen\utils\yaml_model.py

### Class: YamlModel

**Description:**
Base class for yaml model

#### Method: read_yaml

**Description:**
Read yaml file and return a dict

**Arguments:**
```python
def read_yaml(cls: Any, file_path: Path, encoding: str) -> Dict
```

#### Method: from_yaml_file

**Description:**
Read yaml file and return a YamlModel instance

**Arguments:**
```python
def from_yaml_file(cls: Any, file_path: Path) -> Any
```

#### Method: to_yaml_file

**Description:**
Dump YamlModel instance to yaml file

**Arguments:**
```python
def to_yaml_file(self: Any, file_path: Path, encoding: str) -> Any
```


## Module: beegen\utils\__init__.py


## Module: beegen\vectordb\base.py

### Class: VDBRecord

**Description:**
Encapsulates information about a vector's unique identifier and its
payload, which is primarily used as a data transfer object when saving
to vector storage.

Attributes:
    id (str, optional): A unique identifier for the vector. If not
        provided, an random uuid will be assigned.
    vector (List[float]): The numerical representation of the vector.        
    payload (Optional[Dict[str, Any]], optional): Any additional metadata
        or information related to the vector. (default: :obj:`None`)

### Class: VDBQuery

**Description:**
Represents a query to a vector database.

Attributes:
    query_vector (List[float]): The numerical representation of the query
        vector.
    top_k (int, optional): The number of top similar vectors to retrieve
        from the database. (default: :obj:`1`)

#### Method: validate_top_k

**Arguments:**
```python
def validate_top_k(cls: Any, v: int) -> int
```

### Class: VDBResult

**Description:**
Encapsulates the result of a query against a vector database.

Attributes:
    record (VectorRecord): The target vector record.
    similarity (float): The similarity score between the query vector and
        the record.

#### Method: validate_similarity

**Arguments:**
```python
def validate_similarity(cls: Any, v: float) -> float
```

#### Method: construct

**Arguments:**
```python
def construct(cls: Any, similarity: float, id: str, vector: List[Any], payload: Optional[Any]) -> Any
```

### Class: VDBStatus

**Description:**
Vector database status.

Attributes:
    vector_dim (int): The dimention of stored vectors.
    vector_count (int): The number of stored vectors.

#### Method: validate_vector_dim

**Arguments:**
```python
def validate_vector_dim(cls: Any, v: int) -> int
```

#### Method: validate_vector_count

**Arguments:**
```python
def validate_vector_count(cls: Any, v: int) -> int
```

### Class: BaseVectorStore

**Description:**
Abstract base class for vector storage system.

#### Method: add

**Description:**
Saves a list of vector records to the storage.

Args:
    records (List[VectorRecord]): List of vector records to be saved.
    **kwargs (Any): Additional keyword arguments.

Raises:
    RuntimeError: If there is an error during the saving process.

**Arguments:**
```python
def add(self: Any, records: List[Any]) -> Any
```

#### Method: delete

**Description:**
Deletes a list of vectors identified by their IDs from the storage.

Args:
    ids (List[str]): List of unique identifiers for the vectors to be
        deleted.
    **kwargs (Any): Additional keyword arguments.

Raises:
    RuntimeError: If there is an error during the deletion process.

**Arguments:**
```python
def delete(self: Any, ids: List[Any]) -> Any
```

#### Method: status

**Description:**
Returns status of the vector database.

Returns:
    VectorDBStatus: The vector database status.

**Arguments:**
```python
def status(self: Any) -> VDBStatus
```

#### Method: get_payloads_by_vector

**Description:**
Returns payloads of top k vector records that closest to the given
vector.

This function is a wrapper of `BaseVectorStorage.query`.

Args:
    vector (List[float]): The search vector.
    top_k (int): The number of top similer vectors.

Returns:
    List[List[Dict[str, Any]]]: A list of vector payloads retrieved
        from the storage based on similarity to the query vector.

**Arguments:**
```python
def get_payloads_by_vector(self: Any, vector: List[Any], top_k: int) -> List[Any]
```


## Module: beegen\vectordb\milvus.py

#### Function: l2_to_cosine

**Description:**
Convert L2 (Euclidean) distance to Cosine similarity score.

For normalized vectors (unit vectors):
cosine_similarity = 1 - (l2_distance^2 / 2)

For non-normalized vectors:
Need to provide the vector_norm (magnitude of vectors)

Args:
    l2_distance (float): L2 distance between vectors
    vector_norm (float, optional): Norm of the vectors if they're not normalized
    
Returns:
    float: Cosine similarity score in range [-1, 1]

**Arguments:**
```python
def l2_to_cosine(l2_distance: Any, vector_norm: Any) -> None
```

### Class: MilvusStorage

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, config: MilvusConfig) -> None
```

#### Method: from_path

**Description:**
Create a MongoStorage instance from a config file path.

Args:
    path: Path to the mongo config YAML file
    
Returns:
    MongoStorage: A new instance initialized with the config

**Arguments:**
```python
def from_path(cls: Any, path: Union[Any]) -> Any
```

#### Method: _connect

**Description:**
Establish connection to Milvus server.

**Arguments:**
```python
def _connect(self: Any) -> Any
```

#### Method: _disconnect

**Description:**
Close the connection to Milvus server.

**Arguments:**
```python
def _disconnect(self: Any) -> Any
```

#### Method: _load_collection

**Description:**
Get a collection by name and load it into memory.

Args:
    collection_name (str): name of the collection

Returns:
    Collection: Loaded collection object

**Arguments:**
```python
def _load_collection(self: Any, collection_name: str) -> Collection
```

#### Method: _collection_exists

**Arguments:**
```python
def _collection_exists(self: Any, collection_name: str) -> bool
```

#### Method: _delete_collection

**Description:**
Deletes an existing collection from the database.

Args:
    collection (str): Name of the collection to be deleted.

**Arguments:**
```python
def _delete_collection(self: Any, collection_name: str) -> Any
```

#### Method: _generate_collection_name

**Description:**
Generates a unique name for a new collection based on the current
timestamp. Milvus collection names can only contain alphanumeric
characters and underscores.

Returns:
    str: A unique, valid collection name.

**Arguments:**
```python
def _generate_collection_name(self: Any) -> str
```

#### Method: _verify_collection

**Arguments:**
```python
def _verify_collection(self: Any, collection_name: str) -> None
```

#### Method: _get_primary_and_vector_fields

**Description:**
Get primary key and indexed vector field names.

**Arguments:**
```python
def _get_primary_and_vector_fields(self: Any, collection_name: str) -> Tuple[Any]
```

#### Method: _get_collection_info

**Description:**
Retrieves details of an existing collection.

Args:
    collection_name (str): Name of the collection to be checked.

Returns:
    Dict[str, Any]: A dictionary containing details about the
        collection including:
        - id: the id of the collection
        - vector_count: the number of vectors in the collection
        - vector_dim: the dimension of the vectors

**Arguments:**
```python
def _get_collection_info(self: Any, collection_name: str) -> Dict[Any]
```

#### Method: _convert_record_to_milvus_format

**Description:**
Validates and converts VectorRecord instances to the format
expected by Milvus.

Args:
    records (List[VectorRecord]): List of vector records to validate
    and convert.

Returns:
    List[dict]: A list of dictionaries formatted for Milvus insertion.

**Arguments:**
```python
def _convert_record_to_milvus_format(self: Any, collection_name: str, records: List[Any]) -> List[Any]
```

#### Method: _convert_milvus_format_to_record

**Arguments:**
```python
def _convert_milvus_format_to_record(self: Any, collection_name: str, results: List[Any], output_fields: List[Any]) -> List[Any]
```

#### Method: add

**Description:**
Adds a list of vectors to the specified collection.

Args:
    records (List[VectorRecord]): List of vectors to be added.
    **kwargs (Any): Additional keyword arguments pass to insert.

Raises:
    RuntimeError: If there was an error in the addition process.

**Arguments:**
```python
def add(self: Any, collection_name: str, records: List[Any]) -> Any
```

#### Method: delete

**Description:**
Deletes a list of vectors identified by their IDs from the
storage. If unsure of ids you can first query the collection to grab
the corresponding data.

Args:
    ids (List[str]): List of unique identifiers for the vectors to be
        deleted.
    **kwargs (Any): Additional keyword arguments passed to delete.

Raises:
    RuntimeError: If there is an error during the deletion process.

**Arguments:**
```python
def delete(self: Any, collection_name: str, ids: List[Any]) -> Any
```

#### Method: status

**Description:**
Retrieves the current status of the Milvus collection. This method
provides information about the collection, including its vector
dimensionality and the total number of vectors stored.

Returns:
    VectorDBStatus: An object containing information about the
        collection's status.

**Arguments:**
```python
def status(self: Any, collection_name: Any) -> VDBStatus
```

#### Method: _run

**Description:**
Performs similarity search in a vector database collection.

This method searches for vectors similar to the query vector in the specified
collection. It validates the collection and requested output fields, applies
search parameters, and returns formatted results.

Args:
    query (VDBQuery): Input query object 
    **kwargs (Any): Additional keyword arguments passed directly to the 
        underlying search method

Returns:
    List[VDBResult]: List of search results, where each result contains the
        requested output fields and similarity scores. Results are ordered
        by similarity to the query vector.

**Arguments:**
```python
def _run(self: Any, query: VDBQuery) -> List[Any]
```


## Module: beegen\vectordb\__init__.py


## Module: beeportal\beegen_bot.py

### Class: Bot

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, bot_id: str) -> None
```

#### Method: acquire_config

**Arguments:**
```python
def acquire_config(self: Any) -> BotConfig
```


## Module: beeportal\beegen_bot_v2.py

### Class: InputQuery

### Class: VerifyResult

#### Function: parse_model

**Description:**
Parse input text into a specified Pydantic model.

Args:
    input_text: Input string in a format similar to YAML
    model_class: The Pydantic model class to parse into
    
Returns:
    An instance of the specified model class
    
Raises:
    ValueError: If parsing or validation fails

**Arguments:**
```python
def parse_model(input_text: str, model_class: Type[Any]) -> T
```

### Class: Bot

**Description:**
A chatbot class that handles conversations using LLM, document retrieval, and reranking.

This class implements a complete conversation flow including:
- Intent classification
- Document retrieval and reranking
- Handling both casual (chitchat) and information-seeking conversations
- Role-based access control for documents

Attributes:
    bot_id (str): Unique identifier for the bot instance
    bot_store (MongoStorage): Storage for bot configurations and metadata
    bot_config (Dict[str, Any]): Bot-specific configuration settings
    _llm (LLMExecutor): Language model execution handler
    _retriever (VectorRetriever): Document retrieval component
    _reranker (RerankingFactory): Document reranking component

#### Method: __init__

**Description:**
Initialize the Bot instance with necessary components.

Args:
    bot_config (Dict): Configuration dictionary containing LLM, embedding, and reranking settings for the bot
    vec_store (MilvusStorage): Vector storage instance for managing embeddings and similarity search
    doc_store (DocumentStore): Document storage instance for retrieving and managing content
    bot_store (BotStore): Bot configuration storage used for fallback LLM configs when primary configuration is inactive

**Arguments:**
```python
def __init__(self: Any, bot_config: Dict, vec_store: MilvusStorage, doc_store: DocumentStore, bot_store: BotStore) -> None
```

#### Method: _format_documents

**Description:**
Format a list of documents into a single string with separators.

Args:
    documents: List of document dictionaries, each containing a 'content' field
    
Returns:
    String containing all document contents separated by [SEP] tokens

**Arguments:**
```python
def _format_documents(self: Any, documents: List[Any]) -> str
```

#### Method: _create_attached_docs

**Description:**
Create metadata for documents to be attached to LLM requests.

Args:
    documents: List of document dictionaries containing 'id' and optional 'doc' fields
    
Returns:
    List of dictionaries containing document metadata (id and source)

**Arguments:**
```python
def _create_attached_docs(self: Any, documents: List[Any]) -> List[Any]
```


## Module: beeportal\beehi.py

### Class: Bot

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, bot_id: str) -> None
```

#### Method: acquire_config

**Arguments:**
```python
def acquire_config(self: Any) -> BotConfig
```


## Module: beeportal\beehi_v2.py

### Class: InputQuery

### Class: VerifyResult

### Class: BeehiBot

#### Method: __init__

**Description:**
Initialize the Bot instance with necessary components.

Args:
    bot_config (Dict): Configuration dictionary containing LLM, embedding, and reranking settings for the bot
    vec_store (MilvusStorage): Vector storage instance for managing embeddings and similarity search
    doc_store (DocumentStore): Document storage instance for retrieving and managing content
    bot_store (BotStore): Bot configuration storage used for fallback LLM configs when primary configuration is inactive

**Arguments:**
```python
def __init__(self: Any, bot_config: Dict, vec_store: MilvusStorage, doc_store: DocumentStore, bot_store: BotStore) -> None
```

#### Method: _format_documents

**Description:**
Format a list of documents into a single string with separators.

Args:
    documents: List of document dictionaries, each containing a 'content' field
    
Returns:
    String containing all document contents separated by [SEP] tokens

**Arguments:**
```python
def _format_documents(self: Any, documents: List[Any]) -> str
```

#### Method: _create_attached_docs

**Description:**
Create metadata for documents to be attached to LLM requests.

Args:
    documents: List of document dictionaries containing 'id' and optional 'doc' fields
    
Returns:
    List of dictionaries containing document metadata (id and source)

**Arguments:**
```python
def _create_attached_docs(self: Any, documents: List[Any]) -> List[Any]
```


## Module: beeportal\__init__.py


## Module: entrypoints\__init__.py


## Module: entrypoints\openai\api_server.py


## Module: entrypoints\openai\api_server_v2.py

### Class: BotService

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any) -> None
```

#### Function: start_server

**Description:**
Start the FastAPI server with the specified configuration.

**Arguments:**
```python
def start_server(host: str, port: int) -> None
```


## Module: entrypoints\openai\keycloak_utils.py

### Class: KeycloakMiddleware

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, token: Any) -> None
```

#### Method: verify_token

**Arguments:**
```python
def verify_token(self: Any) -> None
```


## Module: entrypoints\openai\__init__.py


## Module: examples\mongo_async_vs_sync_test.py

### Class: MongoConfig

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any) -> None
```

#### Method: uri

**Arguments:**
```python
def uri(self: Any) -> str
```

### Class: PerformanceComparison

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any) -> None
```

#### Method: sync_insert_many

**Arguments:**
```python
def sync_insert_many(self: Any, num_docs: Any) -> None
```

#### Method: sync_find_many

**Arguments:**
```python
def sync_find_many(self: Any, num_queries: Any) -> None
```


## Module: examples\mongo_test.py


## Module: examples\temp.py


## Module: examples\test_fvoc.py

#### Function: make_extraction_request

**Description:**
Make an extraction request to the specified endpoint with timing measurement

Args:
    url: The endpoint URL
    conversation: The conversation text to analyze
    request_time: The timestamp for the request
    token: The authorization token
    
Returns:
    Dict containing the response data and timing information

**Arguments:**
```python
def make_extraction_request(url: str, conversation: str, request_time: str, token: str) -> Dict[Any]
```

#### Function: generate_random_words

**Description:**
Generate a string of n random words.

Args:
    n (int): Number of words to generate
    min_word_length (int): Minimum length of each word
    max_word_length (int): Maximum length of each word
    
Returns:
    str: Space-separated random words

**Arguments:**
```python
def generate_random_words(n: int, min_word_length: int, max_word_length: int) -> str
```

#### Function: get_keycloak_token

**Arguments:**
```python
def get_keycloak_token() -> None
```


## Module: examples\test_graph_state.py

#### Function: tokenize

**Arguments:**
```python
def tokenize(raw_text: str) -> List[Any]
```

#### Function: count_words

**Arguments:**
```python
def count_words(tokens: List[Any]) -> Dict[Any]
```

#### Function: calculate_stats

**Arguments:**
```python
def calculate_stats(word_count: Dict[Any]) -> Dict
```

### Class: NodeStatus

### Class: State

#### Method: update

**Arguments:**
```python
def update(self: Any, node_id: str, data: Any) -> None
```

#### Method: get

**Arguments:**
```python
def get(self: Any, node_id: str) -> Any
```

### Class: Node

#### Method: execute

**Arguments:**
```python
def execute(self: Any, state: State) -> Any
```

#### Method: _check_conditions

**Arguments:**
```python
def _check_conditions(self: Any, state: State) -> bool
```

### Class: Graph

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any) -> None
```

#### Method: add_node

**Arguments:**
```python
def add_node(self: Any, node: Node) -> None
```

#### Method: add_edge

**Arguments:**
```python
def add_edge(self: Any, from_node: str, to_node: str) -> None
```

#### Method: get_execution_order

**Arguments:**
```python
def get_execution_order(self: Any) -> List[Any]
```

#### Method: execute

**Arguments:**
```python
def execute(self: Any, initial_data: Dict[Any]) -> None
```

#### Function: main

**Arguments:**
```python
def main() -> None
```


## Module: examples\test_llm_factory.py


## Module: examples\test_openai_performance.py

#### Function: make_api_request

**Arguments:**
```python
def make_api_request(stream_mode: Any) -> None
```


## Module: examples\test_redis.py

#### Function: create_redis_connection

**Description:**
Creates a connection to Redis server with error handling

Args:
    host (str): Redis host address
    port (int): Redis port number
    password (str): Redis password
    db (int): Redis database number

Returns:
    redis.Redis: Redis connection object

**Arguments:**
```python
def create_redis_connection(host: Any, port: Any, password: Any, db: Any) -> None
```

#### Function: example_usage

**Description:**
Example of how to use the Redis connection

**Arguments:**
```python
def example_usage() -> None
```


## Module: examples\test_tiktoken_azure.py


## Module: examples\test_vllm_api.py


## Module: examples\configs\bee_config_usage.py


## Module: examples\configs\llm_config_usage.py


## Module: examples\configs\milvus_config_usage.py

#### Function: save_and_load_config

**Arguments:**
```python
def save_and_load_config() -> None
```

#### Function: connect_to_milvus

**Description:**
Establish a connection to Milvus server

**Arguments:**
```python
def connect_to_milvus(config: MilvusConfig) -> None
```

#### Function: create_collection

**Description:**
Create a collection based on the provided configuration

**Arguments:**
```python
def create_collection(collection_config: MilvusCollectionConfig) -> None
```

#### Function: main

**Arguments:**
```python
def main() -> None
```


## Module: examples\configs\mongo_config_usage.py

#### Function: connect_to_mongo

**Arguments:**
```python
def connect_to_mongo(config: MongoConfig) -> MongoClient
```

#### Function: main

**Arguments:**
```python
def main() -> None
```


## Module: examples\logs\logs_usage.py


## Module: examples\utils\yaml_model_usage.py

### Class: AppConfig

**Description:**
Application configuration model

#### Function: main

**Arguments:**
```python
def main() -> None
```


## Module: examples\vectordb\base.py


## Module: examples\vectordb\milvus.py


## Module: scripts\ccu_test_llm.py


## Module: scripts\create_random_role_milvus.py


## Module: scripts\DocumentationGenerator.py

### Class: DocGenerator

#### Method: __init__

**Arguments:**
```python
def __init__(self: Any, project_path: str) -> None
```

#### Method: generate_docs

**Description:**
Main method to generate documentation for the entire project.
Returns the complete markdown string.

**Arguments:**
```python
def generate_docs(self: Any) -> str
```

#### Method: _process_file

**Description:**
Process a single Python file and extract its documentation.

**Arguments:**
```python
def _process_file(self: Any, file_path: str) -> Any
```

#### Method: _process_class

**Description:**
Process a class definition and extract its documentation.

**Arguments:**
```python
def _process_class(self: Any, node: Any) -> Any
```

#### Method: _process_function

**Description:**
Process a function definition and extract its documentation.

**Arguments:**
```python
def _process_function(self: Any, node: Any, is_method: bool) -> Any
```

#### Method: _get_function_args

**Description:**
Extract and format function arguments.

**Arguments:**
```python
def _get_function_args(self: Any, node: Any) -> str
```

#### Method: _format_type_annotation

**Description:**
Format complex type annotations (e.g., List[str], Dict[str, int]).

**Arguments:**
```python
def _format_type_annotation(self: Any, node: Any) -> str
```

#### Method: _add_header

**Description:**
Add a markdown header of specified level.

**Arguments:**
```python
def _add_header(self: Any, text: str, level: int) -> Any
```

#### Function: generate_project_docs

**Description:**
Generate markdown documentation for a Python project.

Args:
    project_path: Path to the Python project root directory
    output_file: Name of the output markdown file

**Arguments:**
```python
def generate_project_docs(project_path: str, output_file: str) -> Any
```


## Module: scripts\print_tree_structure.py

#### Function: print_tree

**Arguments:**
```python
def print_tree(directory: Any, prefix: Any) -> None
```


## Module: scripts\push_config_to_mongodb.py


## Module: test\__init__.py


## Module: test\sync_data\sync_data_test.py

#### Function: get_access_token

**Arguments:**
```python
def get_access_token() -> None
```

#### Function: send_request

**Description:**
Send HTTP request with specified type (POST/GET/DELETE).

Args:
    url: API endpoint URL
    request_type: Type of request ('post', 'get', or 'delete')
    bot_id: Bot identifier for query parameter
    payload: Optional dictionary containing request body data (required for POST, optional for DELETE)

Returns:
    Dictionary containing response data

**Arguments:**
```python
def send_request(url: str, method: str, bot_id: str, payload: Optional[Any]) -> Dict
```

#### Function: run_command

**Arguments:**
```python
def run_command(command: str) -> Dict
```

#### Function: main

**Arguments:**
```python
def main() -> None
```


## Module: test\sync_data\validate_milvus_mongo_sync_data.py


## Module: test\sync_data\__init__.py

