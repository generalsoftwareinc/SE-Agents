from pydantic import BaseModel
from typing import Literal

class ResponseEvent(BaseModel):
    type: Literal["assistant","thinking", "tool_call_started", "tool_result", "tool_error"]
    content: str