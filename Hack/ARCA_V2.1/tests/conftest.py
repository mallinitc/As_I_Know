"""Keep V2 API tests isolated from historical application logs."""
import os
import tempfile

os.environ["ARCA_LOG_DIR"] = tempfile.mkdtemp(prefix="arca-test-telemetry-")
