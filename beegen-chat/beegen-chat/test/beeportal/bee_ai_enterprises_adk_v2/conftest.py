import sys
from unittest.mock import MagicMock

# Mock out the beeflow nodes to prevent them from initializing Redis/MongoDB during pytest collection
mock_gcp = MagicMock()
sys.modules['beeflow.nodes.gcp.gcp_retriever_node'] = mock_gcp

import pytest
from pathlib import Path
from dotenv import load_dotenv

_ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT_DIR / ".env", override=False)
