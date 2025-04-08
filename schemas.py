from pydantic import BaseModel

class BaseMessage(BaseModel):
    role: str
    content: str

class AssistantMessage(BaseMessage):
    pass

class ToolMessage(BaseMessage):
    pass