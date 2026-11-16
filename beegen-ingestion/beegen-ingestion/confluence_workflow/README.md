# Confluence Workflow (BeeFlow Version)

BeeFlow-based implementation for Confluence to PostgreSQL sync. This package provides a workflow-based data ingestion framework for synchronizing content from Confluence.

**Note:** This version uses BeeFlow's special service nodes (SQLNode, MongoNode, S3Node, KafkaNode) for storage operations, providing better observability and consistency.

## Architecture

This implementation uses BeeFlow framework with the following components:

### Workflow Structure
```
┌─────────────────────────────────────────────────────────────────┐
│              Confluence Sync Workflow                        │
│  ┌──────────────┐  ┌──────────────┐         │
│  │ initialize    │→ │ route_mode   │         │
│  │ (SQLNode)    │  │ (BranchNode) │         │
│  └──────────────┘  └──────────────┘         │
│         ↓                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐│
│  │fetch_all     │  │fetch_specific │  │fetch_   ││
│  │descendants   │  │pages          │  │active   ││
│  │(CodeNode)    │  │(CodeNode)     │  │pages    ││
│  └──────────────┘  └──────────────┘  │(MongoNode)││
│         ↓              ↓              └──────────┘│
│         └──────────────┴──────────────┐          │
│                ↓                      │          │
│  ┌──────────────┐                     │          │
│  │process_batch │                     │          │
│  │(CodeNode)    │                     │          │
│  └──────────────┘                     │          │
│                ↓                      │          │
│  ┌──────────────┐                     │          │
│  │check_sweep   │                     │          │
│  │(BranchNode)  │                     │          │
│  └──────────────┘                     │          │
│         ↓        ↓                     │          │
│  ┌──────────────┐  ┌──────────────┐   │          │
│  │sweep_delete  │→ │finalize_job  │   │          │
│  │(SQLNode)     │  │(SQLNode)     │   │          │
│  └──────────────┘  └──────────────┘   │          │
│                      ↓                  │          │
│  ┌──────────────┐                       │          │
│  │send_kafka    │                       │          │
│  │(KafkaNode)   │                       │          │
│  └──────────────┘                       │          │
└─────────────────────────────────────────────────────────────────┘
```

### Page Processing Sub-Workflow
```
┌─────────────────────────────────────────────────────────────────┐
│           Page Processing Graph                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
│  │fetch    │→ │transform │→ │convert   │   │
│  │HTML      │  │links    │  │to DOCX  │   │
│  │(CodeNode)│  │(CodeNode)│  │(CodeNode)│   │
│  └─────────┘  └─────────┘  └─────────┘   │
│         ↓                                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
│  │upload   │→ │store    │→ │send     │   │
│  │to S3    │  │to PG    │  │result   │   │
│  │(S3Node) │  │(SQLNode)│  │(CodeNode)│   │
│  └─────────┘  └─────────┘  └─────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Module Structure

```
confluence_workflow/
├── __init__.py                      # Package initialization
├── main.py                          # Main entry point
├── workflow.py                       # Main sync workflow
├── config.py                        # Configuration management
├── workflows/                        # Sub-workflows
│   ├── __init__.py
│   └── page_processing.py           # Page processing sub-workflow
├── functions/                        # Code functions for nodes
│   ├── __init__.py
│   ├── confluence_processor.py      # Confluence API operations
│   ├── storage.py                   # Storage operations (PG, S3, Mongo)
│   ├── postgres_processor.py        # PostgreSQL helpers
│   ├── mongo_processor.py           # MongoDB helpers
│   ├── s3_processor.py             # S3 helpers
│   └── transform.py                 # Data transformation
└── utils/                           # Utilities
    ├── __init__.py
    └── logger.py                    # Logging configuration
```

## BeeFlow Node Usage

| Operation | Node Type | Reason |
|-----------|------------|--------|
| Confluence API calls | `CodeNode` | No dedicated ConfluenceNode |
| PostgreSQL operations | `SQLNode` | Direct asyncpg operations via BeeFlow |
| MongoDB operations | `MongoNode` | Motor async operations via BeeFlow |
| S3 uploads/downloads | `S3Node` | aioboto3 async operations via BeeFlow |
| Kafka notifications | `KafkaNode` | aiokafka async operations via BeeFlow |
| Sync mode routing | `BranchNode` | Conditional logic |
| Batch processing | `CodeNode` | Custom batch logic |

## Sync Modes

### FIRST Mode
- Fetches all descendant pages from specified parent page IDs
- Processes all pages in batches
- Sweeps deleted pages not seen in current sync
- Use case: Initial sync of a space

### PARTIAL Mode
- Fetches only specified page IDs (not descendants)
- Processes pages in batches
- No sweep operation
- Use case: Incremental updates to specific pages

### AUTO Mode
- Queries MongoDB for active parent pages using `MongoNode`
- Fetches descendants of active pages
- Processes pages in batches
- Sweeps deleted pages
- Use case: Scheduled syncs with active page filtering

## Usage

### Command Line
```bash
# First sync (all descendants)
python -m confluence_workflow.main \
  --bot_id <bot_id> \
  --sync_mode FIRST \
  --page_ids '["12345", "67890"]'

# Partial sync (specific pages)
python -m confluence_workflow.main \
  --bot_id <bot_id> \
  --sync_mode PARTIAL \
  --page_ids '["12345", "67890"]'

# Auto sync (active pages from MongoDB)
python -m confluence_workflow.main \
  --bot_id <bot_id> \
  --sync_mode AUTO
```

### Environment Variables
```bash
# Database (PostgreSQL)
POSTGRE_DB=anapp
POSTGRE_USER=devaiplatform
POSTGRES_PASSWORD=your_password
POSTGRE_HOST=localhost
POSTGRE_PORT=5432

# Confluence
CONFLUENCE_URL=https://your-confluence.com
CONFLUENCE_TOKEN=your_api_token

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=aicenter_chatbot

# S3
S3_BUCKET=your_bucket_name
AWS_ENDPOINT_URL=https://your-s3-endpoint.com
AWS_ACCESS_KEY_ID_AI_KNOWLEDGE=your_access_key
AWS_SECRET_ACCESS_KEY_AI_KNOWLEDGE=your_secret_key
S3_BEEGEN_FOLDER=beegen

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=app-beegen-sync-job
```

## Configuration

### WorkflowConfig
```python
from confluence_workflow.config import WorkflowConfig, load_config_from_args

config = WorkflowConfig(
    bot_id="your-bot-id",
    sync_mode="FIRST",
    page_ids=["12345", "67890"],
    batch_size=50,
    limit=0,  # 0 = no limit
    temp_dir="temp_pdfs",
    kafka_topic="app-beegen-sync-job"
)
```

## Functions

### Confluence Functions (`confluence_processor.py`)
- `fetch_pages_from_confluence()` - Fetch pages based on sync mode
- `fetch_descendants_from_confluence()` - Fetch all descendants
- `fetch_specific_pages_from_confluence()` - Fetch specific pages
- `fetch_page_html_content()` - Fetch HTML content
- `absolutize_links()` - Convert relative links to absolute
- `html_to_docx()` - Convert HTML to DOCX
- `get_active_parent_pages()` - Get active parent pages for AUTO mode

### Storage Functions (`storage.py`)
- `initialize_job_in_postgres()` - Create sync job record (SQLNode wrapper)
- `store_document_in_postgres()` - Store document using stored procedure (SQLNode wrapper)
- `sweep_deleted_pages_from_postgres()` - Mark deleted pages (SQLNode wrapper)
- `finalize_job_in_postgres()` - Update job status (SQLNode wrapper)
- `upload_file_to_s3()` - Upload file to S3 (S3Node wrapper)
- `get_active_parent_pages()` - Get active parent pages (MongoNode wrapper)

### PostgreSQL Helper Functions (`postgres_processor.py`)
- `get_job_id_from_postgres()` - Extract job_id from SQLNode output
- `build_sweep_params()` - Build parameters for sweep operation

### S3 Helper Functions (`s3_processor.py`)
- `build_s3_key()` - Build S3 key for document storage
- `build_s3_data()` - Build S3 data for upload

### Transform Functions (`transform.py`)
- `sanitize_title()` - Sanitize title for filenames
- `compute_content_hash()` - Compute MD5 hash
- `extract_page_data()` - Extract relevant page data
- `build_s3_key()` - Build S3 object key
- `build_s3_path()` - Build full S3 path

## Migration from confluence_syncing

This BeeFlow version provides several benefits over the original implementation:

1. **Workflow Visualization** - Built-in Langfuse tracing
2. **Declarative Syntax** - Workflow graph instead of imperative code
3. **Better Testing** - Workflow-level testing possible
4. **Easier Debugging** - Visual workflow graphs
5. **Modularity** - Reusable sub-workflows
6. **Streaming Support** - Built-in streaming via STREAM_SERVICE
7. **Special Service Nodes** - SQLNode, MongoNode, S3Node, KafkaNode for storage operations

## Development

### Adding New Sync Mode
1. Add mode to `BranchNode` cases in [`workflow.py`](workflow.py:92)
2. Implement fetch function in [`functions/confluence_processor.py`](functions/confluence_processor.py:1)
3. Update documentation

### Adding New Storage Backend
1. Implement helper functions in appropriate processor file
2. Update [`WorkflowConfig`](config.py:15) to include new config
3. Add node to workflow if needed

### Adding New Transform Function
1. Add function to [`functions/transform.py`](functions/transform.py:1)
2. Import in [`functions/__init__.py`](functions/__init__.py:1)
3. Use in workflow or sub-workflow

## Dependencies

```txt
beeflow>=0.1.0
atlassian-python-api>=3.0.0
asyncpg>=0.29.0
motor>=3.0.0
aioboto3>=11.0.0
aiokafka>=0.8.0
beautifulsoup4>=4.12.0
html4docx>=0.0.0
python-dotenv>=1.0.0
```

## License

See project root for license information.
