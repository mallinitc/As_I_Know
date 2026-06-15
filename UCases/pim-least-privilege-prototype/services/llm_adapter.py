import json
import time
import urllib.request
from typing import Dict, Any


OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"


def call_ollama(
    prompt: str,
    model: str = "qwen2.5:7b-instruct",
    timeout_seconds: int = 180
) -> Dict[str, Any]:
    """
    Call a local Ollama model using the non-streaming HTTP generate API.
    Returns response text, model name, elapsed seconds, and raw response.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_GENERATE_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    start_time = time.time()

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw_result = json.loads(response.read().decode("utf-8"))

    elapsed_seconds = round(time.time() - start_time, 2)

    return {
        "model": model,
        "response": raw_result.get("response", "").strip(),
        "elapsed_seconds": elapsed_seconds,
        "raw": raw_result
    }
