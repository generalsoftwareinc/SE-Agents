from typing import Literal, Dict, Optional

from pydantic import BaseModel


class ResponseEvent(BaseModel):
    type: Literal["response", "tool_call", "tool_response", "tool_error"]
    content: str


class TextResponseEvent(ResponseEvent):
    """Event for regular text responses from the agent."""
    
    @classmethod
    def from_text(cls, content: str):
        """Create a TextResponseEvent from a text string"""
        return cls(type="response", content=content)


class ToolCallResponseEvent(ResponseEvent):
    """Event for tool calls made by the agent."""
    tool_name: str
    parameters: Dict
    raw_content: Optional[str] = None
    
    @classmethod
    def from_xml(cls, tool_name: str, parameters: Dict, raw_xml: str):
        """Create a ToolCallResponseEvent from parsed XML data"""
        return cls(
            type="tool_call",
            content=raw_xml,  # Keep the original content for backward compatibility
            tool_name=tool_name,
            parameters=parameters,
            raw_content=raw_xml
        )


class ToolResponseEvent(ResponseEvent):
    """Event for tool execution responses."""
    result: str
    tool_name: Optional[str] = None
    
    @classmethod
    def from_execution(cls, result: str, tool_name: Optional[str] = None):
        """Create a ToolResponseEvent from a tool execution result"""
        content = f"<tool_response>\n{result}\n</tool_response>\n"
        return cls(
            type="tool_response",
            content=content,  # Keep the formatted content for backward compatibility
            result=result,
            tool_name=tool_name
        )


class ToolErrorEvent(ResponseEvent):
    """Event for tool execution errors."""
    error_message: str
    raw_xml: Optional[str] = None
    tool_name: Optional[str] = None
    
    @classmethod
    def from_error(cls, error_message: str, raw_xml: Optional[str] = None, tool_name: Optional[str] = None):
        """Create a ToolErrorEvent from an error message"""
        content = f"<tool_error>\n{error_message}"
        if raw_xml:
            content += f"\nRaw XML:\n{raw_xml}"
        content += "\n</tool_error>\n"
        
        return cls(
            type="tool_error",
            content=content,  # Keep the formatted content for backward compatibility
            error_message=error_message,
            raw_xml=raw_xml,
            tool_name=tool_name
        )
