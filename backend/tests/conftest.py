from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4


# Set the test database before pytest imports any app module. Several service
# modules import SQLAlchemy models during collection, so configuring the URL in
# only one test module is too late and makes results dependent on file order.
TEST_DATABASE = Path(tempfile.gettempdir()) / f"contract-review-suite-{uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["LLM_API_KEY"] = ""
os.environ["JWT_SECRET"] = "test-only-secret"
