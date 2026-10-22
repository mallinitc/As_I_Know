"""Keep V2 API tests isolated from historical application logs."""
import os
import tempfile

os.environ["ARCA_LOG_DIR"] = tempfile.mkdtemp(prefix="arca-test-telemetry-")
os.environ["ARCA_DEMO_PERSONA_MODE"] = "true"
os.environ["ARCA_DEPLOYMENT_ENV"] = "development"
os.environ["ARCA_TEST_AUTO_ROLE"] = "1"
