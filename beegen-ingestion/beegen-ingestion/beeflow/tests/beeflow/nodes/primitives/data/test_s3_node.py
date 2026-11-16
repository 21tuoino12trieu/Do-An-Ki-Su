"""Integration tests for S3Node data operations.

This suite exercises end-to-end behavior against an S3-compatible backend:
1) LIST_PATHS  — list objects under a prefix
2) WRITE       — upload bytes from memory
3) READ        — read an object and return bytes + metadata
4) DOWNLOAD_FILE — copy from S3 to local filesystem
5) UPLOAD_FILE   — copy from local filesystem to S3

Expectations:
- Each test asserts a successful status and validates key fields in the
  emitted workflow state (tuples of (node_name, field)).
- Paths returned by the node for S3 objects should start with "s3://".
- Content-type metadata is a string when present.
- The tests assume `S3_MODEL` points to a valid storage configuration and that
  credentials/endpoint are available in the environment.

Note:
- The DELETE test is provided but commented out; enable it if your environment
  allows destructive operations.

Run:
  pytest tests
"""

import io
import pytest

from beeflow.states.local_state import FastIndexerState
from beeflow.nodes.primitives.data.s3_node import S3Node
from beegen.configs.storage.s3_config import S3Operation

S3_MODEL = "aicenter-cua"
TEST_FILE_PATH = "rnd/thaivd/work/cua/origin/sample.csv"
TEST_FOLDER_PATH = "rnd/thaivd/work/cua/origin"
TEST_FILE_CONTENT = b"name,score\nAlice,90\nBob,85"
TEST_CONTENT_TYPE = "text/csv"
LOCAL_DOWNLOAD_DIR = "data"


async def execute_node(op: S3Operation, inputs: dict, name: str):
    node = S3Node(
            name=name,
            resource_key=S3_MODEL,
            operation=op,
            inputs=inputs
    )
    state = await node.simulate(inputs=inputs)
    return state


@pytest.mark.asyncio
async def test_s3_list_files():
    state = await execute_node(S3Operation.LIST_PATHS, {"prefix": TEST_FOLDER_PATH}, name="s3_list")

    paths_key = ("s3_list", "paths")
    status_key = ("s3_list", "status")
    count_key = ("s3_list", "count")

    assert status_key in state
    assert state[status_key] == "success"

    assert paths_key in state
    assert isinstance(state[paths_key], list)

    if count_key in state:
        count = state[count_key]
    else:
        count = 0
    assert isinstance(count, int)
    assert count >= 0


@pytest.mark.asyncio
async def test_s3_write_file():
    inputs = {
        "key": TEST_FILE_PATH,
        "content": io.BytesIO(TEST_FILE_CONTENT),
        "content_type": TEST_CONTENT_TYPE
    }

    state = await execute_node(S3Operation.WRITE, inputs, name="s3_write")

    status_key = ("s3_write", "status")
    doc_path_key = ("s3_write", "document_path")

    assert status_key in state
    assert state[status_key] == "success"
    assert doc_path_key in state
    assert state[doc_path_key].endswith(TEST_FILE_PATH)


@pytest.mark.asyncio
async def test_s3_read_file():
    state = await execute_node(S3Operation.READ, {"key": TEST_FILE_PATH}, name="s3_read")

    status_key = ("s3_read", "status")
    doc_bytes_key = ("s3_read", "document_bytes")
    doc_path_key = ("s3_read", "document_path")
    content_type_key = ("s3_read", "content_type")

    assert status_key in state
    assert state[status_key] == "success"

    assert doc_bytes_key in state
    assert isinstance(state[doc_bytes_key], bytes)
    assert b"Alice" in state[doc_bytes_key]

    assert doc_path_key in state
    assert state[doc_path_key].startswith("s3://")

    assert content_type_key in state
    assert isinstance(state[content_type_key], str)


# @pytest.mark.asyncio
# async def test_s3_delete_file():
#     state = await execute_node(S3Operation.DELETE, {"key": TEST_FILE_PATH}, name="s3_delete")

#     status_key = ("s3_delete", "status")
#     doc_path_key = ("s3_delete", "document_path")

#     assert status_key in state
#     assert state[status_key] == "success"
#     assert doc_path_key in state
#     assert state[doc_path_key].startswith("s3://")


@pytest.mark.asyncio
async def test_s3_download_file():
    inputs = {
        "s3_file_path": TEST_FILE_PATH,
        "local_dir": LOCAL_DOWNLOAD_DIR
    }
    state = await execute_node(S3Operation.DOWNLOAD_FILE, inputs, name="s3_download")

    status_key = ("s3_download", "status")
    local_file_key = ("s3_download", "local_file_path")
    doc_path_key = ("s3_download", "document_path")

    assert status_key in state
    assert state[status_key] == "success"

    assert local_file_key in state
    assert state[local_file_key].startswith(LOCAL_DOWNLOAD_DIR)

    assert doc_path_key in state
    assert state[doc_path_key].startswith("s3://")


@pytest.mark.asyncio
async def test_s3_upload_file():
    inputs = {
        "local_file_path": f"{LOCAL_DOWNLOAD_DIR}/sample.csv",
        "s3_file_path": TEST_FILE_PATH,
        "content_type": TEST_CONTENT_TYPE
    }
    state = await execute_node(S3Operation.UPLOAD_FILE, inputs, name="s3_upload")

    status_key = ("s3_upload", "status")
    doc_path_key = ("s3_upload", "document_path")

    assert status_key in state
    assert state[status_key] == "success"
    assert doc_path_key in state
    assert state[doc_path_key].startswith("s3://")