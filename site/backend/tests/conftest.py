import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def tool_response(name: str, args: dict, usage: dict | None = None) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "call_1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
                    ],
                }
            }
        ],
        "usage": usage or {"prompt_tokens": 100, "completion_tokens": 30},
    }


@pytest.fixture
def make_tool_response():
    return tool_response
