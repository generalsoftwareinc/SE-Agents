from typing import Literal

from pydantic import BaseModel


class ResponseEvent(BaseModel):
    type: Literal["assistant", "thinking", "tool_call", "tool_response", "tool_error"]
    content: str
