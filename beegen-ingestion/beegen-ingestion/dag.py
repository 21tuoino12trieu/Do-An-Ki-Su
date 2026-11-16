"""
Airflow DAG for Confluence to PostgreSQL Sync using Kubernetes Pods

This DAG implements unified sync logic across three modes:

Sync Modes:
- FIRST: Syncs pages from specified parent page IDs with move/delete detection
- PARTIAL: Syncs specific pages without move/delete detection
- AUTO: Syncs all pages with sync_mode='active' with move/delete detection

Task Flow:
    start_flow → determine_sync_mode → confluence_sync → end_flow

Key Features:
- Auto-determines sync mode based on input parameters
- Each sync runs in isolated Kubernetes pod with automatic cleanup
- Built-in retry logic (1 retry = total 2 attempts) and execution timeout (2 hours)
- Email notifications on failure
- Structured logging to Kubernetes stdout

All parameters are passed via dag_run.conf or params.
"""

import logging
from datetime import datetime, timedelta
import pendulum
from airflow.models import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from utils.kubernetes_pod_operator import KubernetesPodOperatorCustom
from airflow.utils.trigger_rule import TriggerRule
from airflow.models import Param
from airflow.providers.cncf.kubernetes.secret import Secret

# Timezone configuration
local_tz = pendulum.timezone("Asia/Ho_Chi_Minh")
dag_logger = logging.getLogger("airflow.task")

ai_extra_secret = Secret(
    deploy_type="env",
    deploy_target=None,
    secret="ai-extra-secret"
)

# Default arguments
default_args = {
    "owner": "quanpv.os",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email": ["quanpv.os@mbbank.com.vn"],
    "email_on_failure": True,
    "email_on_retry": False,
}

def determine_sync_mode(**context):
    """
    Determine which sync mode to use based on input parameters.

    Logic:
    - If 'first_syncing' parameter provided -> FIRST mode (syncs from parent page IDs)
    - Elif 'page_ids' parameter provided -> PARTIAL mode (syncs specific pages only)
    - Else -> AUTO mode (syncs all active pages from MongoDB)

    Returns:
        sync_mode: 'FIRST', 'PARTIAL', or 'AUTO'
    """
    dag_run_conf = context.get('dag_run').conf or {}
    params = context.get('params', {})

    # Get parameters (dag_run.conf takes precedence over params)
    first_syncing = dag_run_conf.get('first_syncing') or params.get('first_syncing', '')
    page_ids = dag_run_conf.get('page_ids', params.get('page_ids', []))
    page_ids = page_ids if page_ids is not None else []

    print(f"Determining sync mode...")
    print(f"  First Syncing: '{first_syncing}'")
    print(f"  Page IDs: {page_ids}")

    # Decision logic
    if first_syncing:
        sync_mode = 'FIRST'
        print(f"→ Sync mode: FIRST for {len(page_ids)} parent pages")
    elif page_ids:
        sync_mode = 'PARTIAL'
        print(f"→ Sync mode: PARTIAL for {len(page_ids)} pages")
    else:
        sync_mode = 'AUTO'
        print(f"→ Sync mode: AUTO")

    # Push sync_mode to XCom for downstream tasks
    context['ti'].xcom_push(key='sync_mode', value=sync_mode)
    return sync_mode


# DAG definition
with DAG(
    dag_id='confluence_sync_kubernetes',
    default_args=default_args,
    description='Confluence to PostgreSQL sync with Kubernetes pods (FIRST/PARTIAL/AUTO modes)',
    start_date=datetime(2026, 1, 1, 0, 0, 0, tzinfo=local_tz),
    schedule='0 9,11,13,15,17,19 * * *',  # Every 2 hours with specific time
    catchup=False,
    tags=["confluence", "sync", "kubernetes", "knowledge-base", "auto"],
    max_active_runs=3,
    dagrun_timeout=timedelta(hours=4),
    params={
        "page_ids": Param(
            default=[],
            type="array",
            description="List of parent page IDs for FIRST sync, or specific page IDs for PARTIAL sync. Null value for AUTO mode"
        ),
        "first_syncing": Param(
            default=False,
            type="boolean",
            description="Flag to trigger FIRST mode (sync from parent page IDs with move/delete detection)"
        ),
        "bot_id": Param(
            default="",
            type="string",
            description="Bot ID for tracking sync operations"
        ),
        "confluence_url": Param(
            default="",
            type="string",
            description="Confluence base URL"
        ),
        "confluence_token": Param(
            default="",
            type="string",
            description="Confluence API token"
        ),
        "batch_size": Param(
            default=50,
            type="integer",
            description="Batch size for fetching pages"
        ),
        "limit": Param(
            default=0,
            type="integer",
            description="Limit number of pages to process"
        ),
        "log_level": Param(
            default="INFO",
            type="string",
            description="Log level (DEBUG, INFO, WARNING, ERROR)"
        ),
    }
) as dag:

    # ========================================================================
    # START
    # ========================================================================
    start_flow = EmptyOperator(
        task_id="start_flow",
        doc="Start of the sync workflow"
    )

    # ========================================================================
    # DETERMINE SYNC MODE
    # ========================================================================
    determine_sync_mode_task = PythonOperator(
        task_id='determine_sync_mode',
        python_callable=determine_sync_mode,
        provide_context=True,
        doc="Determines which sync mode to use (FIRST, PARTIAL, or AUTO)"
    )

    # ========================================================================
    # CONFLUENCE SYNC (UNIFIED)
    # ========================================================================
    confluence_sync = KubernetesPodOperatorCustom(
        task_id="confluence_sync",
        name="confluence-sync",
        namespace="ai-platform",
        image="harbor-tanzu-dev.mbbank.com.vn/aicenter/beegen-sync-job:v1.0.0",
        image_pull_policy="Always",
        cmds=["sh", "-c"],
        arguments=[
            "echo 'AES_GCM_SALT=' $AES_GCM_SALT && "
            "python -m confluence_workflow.main "
            "--sync_mode '{{ ti.xcom_pull(task_ids='determine_sync_mode') }}' "
            "--page_ids '{{ dag_run.conf.get('page_ids', params.page_ids) | tojson }}' "
            "--bot_id '{{ dag_run.conf.get('bot_id', params.bot_id) }}' "
            "--confluence_url '{{ dag_run.conf.get('confluence_url', params.confluence_url) }}' "
            "--confluence_token '{{ dag_run.conf.get('confluence_token', params.confluence_token) }}' "
            "--batch_size '{{ dag_run.conf.get('batch_size', params.batch_size) }}' "
            "--limit '{{ dag_run.conf.get('limit', params.limit) }}' "
            "--log_level '{{ dag_run.conf.get('log_level', params.log_level) }}' "
        ],
        container_resources={
            "requests": {"memory": "2Gi", "cpu": "2"},
            "limits": {"memory": "12Gi", "cpu": "6"}
        },
        env_vars={
            "PYTHONUNBUFFERED": "1",
            "TZ": "Asia/Ho_Chi_Minh",
        },
        secrets=[ai_extra_secret],
        retries=1,
        retry_delay=timedelta(minutes=3),
        execution_timeout=timedelta(hours=4),
        get_logs=True,
        is_delete_operator_pod=True,
        do_xcom_push=True,
        startup_timeout_seconds=600,
        labels={
            "app": "confluence-sync",
            "mode": "unified",
            "owner": "quanpv.os"
        },
        doc="""
        Unified Confluence sync task that handles three modes:
        - FIRST: Syncs pages from specified parent page IDs with move/delete detection
        - PARTIAL: Syncs specific pages without move/delete detection
        - AUTO: Syncs all pages with sync_mode='active' with move/delete detection
        """
    )

    # ========================================================================
    # END
    # ========================================================================
    end_flow = EmptyOperator(
        task_id="end_flow",
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
        doc="End of the sync workflow"
    )

    # ========================================================================
    # TASK DEPENDENCIES
    # ========================================================================
    start_flow >> determine_sync_mode_task >> confluence_sync >> end_flow


# ============================================================================

# DAG Documentation
# ============================================================================
dag.doc_md = """
# Confluence to PostgreSQL Sync DAG (Kubernetes Version)

## Overview

This DAG synchronizes Confluence pages to PostgreSQL using Kubernetes pods. It supports three sync modes with automatic mode detection based on input parameters.

### Task Flow

```
start_flow → determine_sync_mode → confluence_sync (K8s Pod) → end_flow
```

### Key Features

- **Auto mode detection**: Determines sync mode (FIRST/PARTIAL/AUTO) based on input parameters
- **Isolated execution**: Each sync runs in its own Kubernetes pod with automatic cleanup
- **Built-in resilience**: 1 retry (2 total attempts) with 5-minute delay, 2-hour execution timeout
- **Failure handling**: Email notifications on task failure
- **Structured logging**: All logs output to Kubernetes stdout for easy troubleshooting

---

## Sync Modes

### FIRST Mode
- **Trigger**: Provide `first_syncing=True` and `page_ids` parameter
- **Behavior**:
  - Loops through each parent page ID in `page_ids` (if it not provided, it will be fetch from Mongo)
  - Gets all descendant pages for each parent page
  - Detects page moves (parent changes)
  - Detects deleted pages (sweep)
- **Use Case**: Initial sync or full sync from specific parent pages
- **Resources**: 2-4 CPU, 2-4Gi RAM

### PARTIAL Mode
- **Trigger**: Provide `page_ids` parameter without `first_syncing`
- **Behavior**:
  - Fetches only the specified pages (not descendants)
  - Detects content changes
  - Skips move/delete detection
- **Use Case**: Manual/API-triggered ad-hoc updates for specific pages
- **Resources**: 2-4 CPU, 2-4Gi RAM

### AUTO Mode
- **Trigger**: No parameters provided (scheduled run without first_syncing/page_ids)
- **Behavior**:
  - Queries MongoDB for parent pages with `sync_mode='True'` (active pages)
  - Syncs all descendant pages from these active parent pages
  - Detects content changes and updates pages
  - Detects page moves (parent changes)
  - Detects deleted pages (sweep)
  - Excludes pages marked as inactive in MongoDB (`sync_mode='False'`)
- **Use Case**: Automatic sync of all active parent pages from MongoDB (Every 2 hours)
- **Resources**: 2-4 CPU, 2-4Gi RAM

---

## Parameters

All parameters can be passed via `dag_run.conf` when triggering the DAG:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `first_syncing` | boolean | False | Flag to trigger FIRST mode (sync from parent page IDs) |
| `page_ids` | array | [] | Parent page IDs for FIRST mode, or specific page IDs for PARTIAL mode |
| `bot_id` | string | "" | Bot ID for tracking sync operations |
| `confluence_url` | string | "" | Confluence base URL |
| `confluence_token` | string | "" | Confluence API token (PAT) - Authentication uses API token |
| `batch_size` | integer | 50 | Batch size for fetching pages |
| `limit` | integer | null | Limit number of pages (for testing) |
| `log_level` | string | INFO | Log level (DEBUG, INFO, WARNING, ERROR) |
| `enable_kafka` | boolean | true | Enable Kafka log forwarding |
| `temp_dir` | string | temp_pdfs | Temporary directory for PDF files |

## Triggering

### Scheduled Run (AUTO sync for active pages)
Runs automatically every 2 hours (9, 11, 13, 15, 17) without parameters.
Queries MongoDB for parent pages with `sync_mode='True'` (active) and syncs all their descendant pages.

### Manual Run via UI
1. Go to Airflow UI → DAGs → confluence_sync_kubernetes
2. Click "Trigger DAG w/ config"
3. Provide configuration:

**FIRST sync (sync from parent page IDs):**
```json
{
  "first_syncing": true,
  "page_ids": [],
  "bot_id": "your_bot_id",
  "confluence_url": "https://your-confluence.com",
  "confluence_token": "your_api_token",
  "batch_size": 100,
  "log_level": "INFO"
}
```

**PARTIAL sync (sync specific pages only):**
```json
{
  "page_ids": ["123456", "789012"],
  "bot_id": "your_bot_id",
  "confluence_url": "https://your-confluence.com",
  "confluence_token": "your_api_token",
  "batch_size": 50,
  "log_level": "INFO"
}
```

### Manual Run via REST API

**FIRST sync (sync from parent page IDs):**
```bash
curl -X POST http://localhost:8080/api/v1/dags/confluence_sync_kubernetes/dagRuns \
  -H "Content-Type: application/json" \
  -u REPLACE_WITH_LOCAL_SECRET \
  -d '{
    "conf": {
      "first_syncing": true,
      "page_ids": [],
      "bot_id": "your_bot_id",
      "confluence_url": "https://your-confluence.com",
      "confluence_token": "your_api_token",
      "batch_size": 100
    }
  }'
```

**PARTIAL sync (sync specific pages only):**
```bash
curl -X POST http://localhost:8080/api/v1/dags/confluence_sync_kubernetes/dagRuns \
  -H "Content-Type: application/json" \
  -u REPLACE_WITH_LOCAL_SECRET \
  -d '{
    "conf": {
      "page_ids": ["123456", "789012"],
      "bot_id": "your_bot_id",
      "confluence_url": "https://your-confluence.com",
      "confluence_token": "your_api_token"
    }
  }'
```

## Technical Details

| Setting | Value |
|---------|-------|
| Schedule | Every 2 hours (9, 11, 13, 15, 17 UTC+7) |
| Max Active Runs | 3 |
| DAG Run Timeout | 2 hours |
| Pod Retry Attempts | 1 retry (2 total attempts) |
| Retry Delay | 5 minutes |
| Pod Startup Timeout | 10 minutes |
| Pod Execution Timeout | 2 hours |
| Container | `harbor-tanzu-dev.mbbank.com.vn/aicenter/beegen-sync-job:v1.0.0` |
| CPU Requests/Limits | 2 / 4 cores |
| Memory Requests/Limits | 2Gi / 4Gi |
| Namespace | `ai-platform` |

---

## Monitoring

- **Airflow UI**: Task logs, execution time, status
- **Kubernetes**: `kubectl logs -n ai-platform <pod-name>`
- **Database**: Query `knowledge_base.sync_jobs` table

## Troubleshooting

**Pod startup timeout:**
- Check Harbor registry accessibility
- Verify image exists and is pullable

**Missing parameters:**
- All required parameters must be passed via `dag_run.conf`
- Check that Confluence API token is provided (`confluence_token`)
- For FIRST mode, ensure `first_syncing=true` and `page_ids` contains parent page IDs

**Out of memory:**
- Large parent page hierarchies may need resource limit increases
- Consider batching for very large page trees (10k+ pages)

**Sync not fetching expected pages:**
- For FIRST mode: Verify `page_ids` contains parent page IDs, not leaf page IDs
- For AUTO mode: Check MongoDB for pages with correct `sync_mode` values
- For PARTIAL mode: Verify `page_ids` contains the exact page IDs to sync
"""
