"""Keep the complete automated test suite offline regardless of local .env settings."""
import os
import tempfile

os.environ["LLM_PROVIDER"] = "mock"
os.environ["ARCA_CHANGE_EXTRACTOR"] = "mock"
os.environ["ARCA_INVESTIGATION_MODEL"] = "mock"
os.environ["ARCA_MODE"] = "mock"
os.environ["ARCA_LOG_DIR"] = tempfile.mkdtemp(prefix="arca-test-telemetry-")
