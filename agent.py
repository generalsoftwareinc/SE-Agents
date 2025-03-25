import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, Generator, List, Optional, Tuple, Union

from openai import Client

from system_prompt import system_prompt
from tools import DuckDuckGoSearch, Tool


class Agent:
    def __init__(
        self,
        api_key: str,
        model: str,
        tools: List[Tool] = None,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        self.client = Client(api_key=api_key, base_url=base_url)
        self.model = model
        self.tools = {tool.name: tool for tool in (tools or [])}
        # Format the tools section of the system prompt
        tools_section = ""
        for tool in self.tools.values():
            # Tool header
            tools_section += f"## {tool.name}\n"
            tools_section += f"{tool.description}\n"
            tools_section += "Parameters:\n"

            # Parameters
            for name, param in tool.parameters.items():
                required = "(required)" if param.get("required", False) else ""
                tools_section += (
                    f"- {name}: {param.get('description', '')} {required}\n"
                )

            # Usage example
            tools_section += "Usage:\n"
            tools_section += f"<{tool.name}>\n"
            for name in tool.parameters:
                tools_section += f"<{name}>{name} here</{name}>\n"
            tools_section += f"</{tool.name}>\n\n"

        # Replace the tools template with the formatted tools section
        self.messages: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": system_prompt.replace(
                    "{% for tool in tools %}\n## {{ tool.name }}\n{{ tool.description }}\nParameters:\n{% for name, param in tool.parameters.items() %}\n- {{ name }}: {{ param.description }} {% if param.required %}(required){% endif %}\n{% endfor %}\nUsage:\n<{{ tool.name }}>\n{% for name, param in tool.parameters.items() %}<{{ name }}>{{ name }} here</{{ name }}>\n{% endfor %}</{{ tool.name }}>\n\n{% endfor %}",
                    tools_section,
                ),
            }
        ]

    def _parse_tool_call(
        self, message: str
    ) -> tuple[Optional[Dict[str, Dict[str, str]]], Optional[str]]:
        """Parse XML-formatted tool calls from the assistant's message.
        Handles tool calls both directly in the message and inside code blocks.

        Returns:
            tuple: (tool_call_dict, error_message)
                - tool_call_dict: Dictionary with tool name as key and parameters as values, or None if parsing failed
                - error_message: Error message if parsing failed, or None if successful
        """
        # Look for tool calls inside code blocks first
        code_block_match = re.search(
            r"```(?:xml|tool_code)?\s*\n?(.*?)\n?```", message, re.DOTALL
        )
        if code_block_match:
            message = code_block_match.group(1)

        # Skip thinking tags - they're not tool calls
        if "<thinking>" in message or "</thinking>" in message:
            # Remove thinking tags and their content for tool parsing (case-insensitive and handles whitespace)
            message = re.sub(
                r"<\s*thinking[^>]*>.*?<\s*/\s*thinking\s*>",
                "",
                message,
                flags=re.DOTALL | re.IGNORECASE,
            )

        valid_tool_patterns = []
        for tool_name in self.tools.keys():
            pattern = f"<{tool_name}>(.*?)</{tool_name}>"
            valid_tool_patterns.append((tool_name, pattern))
        
        for tool_name, pattern in valid_tool_patterns:
            tool_match = re.search(pattern, message, re.DOTALL)
            if tool_match:
                tool_content = tool_match.group(1)
                break
        else:
            xml_open = re.search(r"<([^>]+)>", message)
            xml_close = re.search(r"</([^>]+)>", message)
            if (
                xml_open
                and xml_close
                and xml_open.group(1) != "thinking"
                and xml_close.group(1) != "thinking"
                and any(tool_name.startswith(xml_open.group(1)) or xml_open.group(1).startswith(tool_name) for tool_name in self.tools.keys())
            ):
                return (
                    None,
                    "Malformed tool call format. Please use the format: <tool_name>\n<param>value</param>\n</tool_name>",
                )
            return None, None

        # Parse parameters
        params = {}
        try:
            root = ET.fromstring(f"<root>{tool_content}</root>")
            for child in root:
                params[child.tag] = child.text.strip() if child.text else ""
        except ET.ParseError as e:
            error_msg = f"Error parsing tool parameters: {str(e)}. Please use valid XML format for parameters."
            return None, error_msg

        return {tool_name: params}, None

    def _execute_tool(self, tool_name: str, params: Dict[str, str]) -> tuple[str, bool]:
        """Execute a tool with the given parameters and return the result and success status.

        Returns:
            tuple: (result, success)
                - result: The tool execution result or error message
                - success: True if execution was successful, False if there were errors
        """
        tool = self.tools.get(tool_name)
        if not tool:
            return f"Unknown tool: {tool_name}", False

        errors = tool.validate_parameters(params)
        if errors:
            return "Error: " + "\n".join(errors), False

        try:
            result = tool.execute(**params)
            return result, True
        except Exception as e:
            return f"Tool error: {str(e)}", False

    def process_message(
        self, user_input: str, stream: bool = False
    ) -> Generator[Tuple[str, str], None, None]:
        """Process a user message and yield responses (assistant messages and tool results).

        This method handles the conversation loop, including tool calls and user interactions.
        For the ask_followup_question tool, it yields a special response type that signals
        the main loop to get user input and then continue the conversation with that input.
        """
        self.messages.append({"role": "user", "content": user_input})
        continue_conversation = True

        while continue_conversation:
            response = self.client.chat.completions.create(
                model=self.model, messages=self.messages, stream=stream
            )

            full_response = ""

            if stream:
                chunk_counting = 0
                in_xml = False
                tool_detected = False
                
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        
                        if "<" in content and not in_xml:
                            in_xml = True
                            chunk_counting = 1
                        
                        elif in_xml:
                            if chunk_counting < 10:
                                chunk_counting += 1
                            elif chunk_counting == 10:
                                for tool_name in self.tools.keys():
                                    if f"<{tool_name}" in full_response:
                                        tool_detected = True
                                        break
                                if not tool_detected:
                                    in_xml = False
                        # if not in_xml:        # Uncomment to avoid showing the XMLs in the stream.
                        yield ("assistant", content)
                
                if tool_detected:
                    tool_call, _ = self._parse_tool_call(full_response)
                    if tool_call:
                        tool_name = list(tool_call.keys())[0]
                        tool_params = tool_call[tool_name]
                        tool_result, _ = self._execute_tool(tool_name, tool_params)
                        yield ("tool", tool_result)
                        self.messages.append(
                            {"role": "user", "content": f"Tool result: {tool_result}"}
                        )
                
                # Add a newline after each complete assistant response if not empty
                if full_response.strip() and not tool_detected:
                    yield ("assistant", "\n")
            else:
                # Non-streaming response
                full_response = response.choices[0].message.content
                if full_response: # Check added in case response is empty
                    yield ("assistant", full_response)


            self.messages.append({"role": "assistant", "content": full_response})

            # Check for tool calls
            tool_call, error_message = self._parse_tool_call(full_response)

            if error_message:
                # Provide feedback about the tool call format error
                feedback = f"Tool call error: {error_message}\n\nPlease try again with the correct format."
                yield ("tool", feedback)

                # Add the error feedback to the conversation history
                self.messages.append({"role": "user", "content": feedback})
                # Continue the conversation to allow the AI to try again
                continue

            elif tool_call:
                tool_name = list(tool_call.keys())[0]
                tool_params = tool_call[tool_name]

                # Execute the tool
                tool_result, success = self._execute_tool(tool_name, tool_params)
                yield ("tool", tool_result)

                # Add the tool result to the conversation history
                self.messages.append(
                    {"role": "user", "content": f"Tool result: {tool_result}"}
                )

                # If there was a parameter validation error, provide a hint about the correct format
                if not success:
                    tool = self.tools.get(tool_name)
                    if tool:
                        param_info = "\n".join(
                            [
                                f"- {name}: {config.get('description', '')} ({'required' if config.get('required') else 'optional'}, type: {config.get('type', 'string')})"
                                for name, config in tool.parameters.items()
                            ]
                        )
                        hint = f"Please try again with the correct parameters for {tool_name}:\n{param_info}"
                        self.messages[-1]["content"] += f"\n\n{hint}"
            else:
                # If no tool call, assume the task is complete and end the conversation
                continue_conversation = False
