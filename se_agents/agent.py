import re
import xml.etree.ElementTree as ET
from pprint import pprint
from typing import AsyncGenerator, Dict, List, Optional, Union

from openai import Client

from se_agents.prompts.additional_context import prompt as additional_context_prompt
from se_agents.prompts.custom_instructions import prompt as custom_instructions_prompt
from se_agents.prompts.description import prompt as description_prompt
from se_agents.prompts.objective import prompt as objective_prompt
from se_agents.prompts.rules import prompt as rules_prompt
from se_agents.prompts.tool_calling import prompt as tool_calling_prompt
from se_agents.prompts.tool_calling import tools_placeholder
from se_agents.schemas import ResponseEvent
from se_agents.tools import Tool

TOKEN_LIMIT = 80000


class Agent:
    def __init__(
        self,
        # Core agent config
        name: str = None,
        token_limit: int = TOKEN_LIMIT,
        # OpenAI config
        api_key: str = None,
        model: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        # Tool config
        tools: List[Tool] = None,
        # Prompt config
        description: Union[str, None] = None,
        rules: Union[str, List[str], None] = None,
        objective: Union[str, List[str], None] = None,
        instructions: Union[str, List[str], None] = None,
        additional_context: Union[str, List[str], None] = None,
        add_tool_instrutions: bool = True,
        add_default_rules: bool = True,
        add_default_objective: bool = True,
        # Message config
        initial_messages: Optional[List[Dict[str, str]]] = None,
        wrap_response_chunks: bool = False,
    ):
        # Core agent config
        self.name = name
        self.token_limit = token_limit

        # OpenAI config
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.client = (
            Client(api_key=api_key, base_url=base_url) if api_key and model else None
        )

        # Tool config
        self.tools = tools or []

        # Prompt config
        self._custom_description = description
        self._custom_rules = rules
        self._custom_objective = objective
        self.add_tool_instrutions = add_tool_instrutions
        self.add_default_rules = add_default_rules
        self.add_default_objective = add_default_objective
        self._custom_instructions = instructions
        self._additional_context = additional_context
        self.wrap_response_chunks = wrap_response_chunks

        # Message config
        system_message = self._add_system_prompt()
        if initial_messages:
            self.messages: List[Dict[str, str]] = [system_message] + initial_messages
        else:
            self.messages: List[Dict[str, str]] = [system_message]

        # Debug output
        print("--- Initial System Prompt (Processed) ---")
        print(self.messages[0]["content"])
        print("---------------------------------------")
        if initial_messages:
            print("--- Initial Conversation Context ---")
            for msg in self.messages[1:]:
                print(f"{msg['role'].capitalize()}: {msg['content'][:100]}...")
            print("------------------------------------")

    def _section_to_str(self, section):
        if section is None:
            return ""
        if isinstance(section, list):
            return "\n".join(section)
        return section

    def _add_system_prompt(self):
        # Format the tools section of the system prompt
        tools_section = ""
        if self.add_tool_instrutions:
            for tool in self.tools:
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
                tools_section += "<tool_call>\n"  # Add opening tool_call tag
                tools_section += f"<{tool.name}>\n"
                for name in tool.parameters:
                    tools_section += f"<{name}>{name} here</{name}>\n"
                tools_section += f"</{tool.name}>\n"
                tools_section += "</tool_call>\n\n"  # Add closing tool_call tag

        # Define the exact placeholder string from system_prompt.py
        placeholder = tools_placeholder

        # Description section
        if self._custom_description is not None:
            description_section = self._custom_description
        else:
            description_section = description_prompt

        # Rules section
        if self._custom_rules is not None:
            rules_section = self._section_to_str(self._custom_rules)
        elif self.add_default_rules:
            rules_section = rules_prompt
        else:
            rules_section = ""

        # Objective section
        if self._custom_objective is not None:
            objective_section = self._section_to_str(self._custom_objective)
        elif self.add_default_objective:
            objective_section = objective_prompt
        else:
            objective_section = ""

        # Tool calling instructions
        tool_calling_section = tool_calling_prompt if self.add_tool_instrutions else ""

        # Compose the full prompt
        full_prompt = (
            description_section
            + ("\n" + tool_calling_section if tool_calling_section else "")
            + ("\n" + rules_section if rules_section else "")
            + ("\n" + objective_section if objective_section else "")
        )

        # Add additional context if provided
        if self._additional_context is not None:
            context_str = self._section_to_str(self._additional_context)
            full_prompt += "\n" + additional_context_prompt.replace(
                "{additional_context}", context_str
            )

        # Add custom instructions if provided
        if self._custom_instructions is not None:
            instructions_str = self._section_to_str(self._custom_instructions)
            full_prompt += "\n" + custom_instructions_prompt.replace(
                "{custom_instructions}", instructions_str
            )

        return {
            "role": "system",
            "content": full_prompt.replace(placeholder, tools_section),
        }

    def _parse_tool_call(
        self, message: str
    ) -> tuple[Optional[Dict[str, Dict[str, str]]], Optional[str], Optional[str]]:
        """Parse XML-formatted tool calls from the assistant's message.
        Handles tool calls both directly in the message and inside code blocks.

        Returns:
            tuple: (tool_call_dict, error_message, raw_tool_call_xml)
                - tool_call_dict: Dictionary with tool name as key and parameters as values, or None if parsing failed
                - error_message: Error message if parsing failed, or None if successful
                - raw_tool_call_xml: The raw XML string of the tool call, or None if not found/parsed
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

        tool_call_match = re.search(r"<tool_call>(.*?)</tool_call>", message, re.DOTALL)
        if tool_call_match:
            tool_call_content = tool_call_match.group(1)
            tool_name_match = re.search(
                r"<([^>]+)>(.*?)</\1>", tool_call_content, re.DOTALL
            )
            if tool_name_match:
                tool_name = tool_name_match.group(1)
                tool_content = tool_name_match.group(2)
                raw_tool_call_xml = tool_call_match.group(
                    0
                )  # Capture the full <tool_call>...</tool_call>
            else:
                return (
                    None,
                    "Malformed tool call format. Please use the format: <tool_call><tool_name>...</tool_name></tool_call>",
                    None,
                )
        else:
            # No <tool_call> tag found
            return None, None, None

        # Use the extracted tool_name and tool_content
        tool = self._get_tool_by_name(tool_name)
        if not tool:
            return None, f"Unknown tool: {tool_name}"

        params = {}
        try:
            temp_root_str = f"<root>{tool_content}</root>"
            root = ET.fromstring(temp_root_str)

            expected_params = set(tool.parameters.keys())
            found_tags = {child.tag for child in root}

            if not found_tags.issubset(expected_params):
                return (
                    None,
                    f"Unexpected parameters in tool call for {tool_name}. Expected: {', '.join(expected_params)}",
                    raw_tool_call_xml,
                )

            params = {
                child.tag: child.text.strip() if child.text else "" for child in root
            }

        except ET.ParseError as e:
            return (
                None,
                f"Malformed XML in tool call: {str(e)} \n Please check the format.",
                raw_tool_call_xml,
            )

        return {tool_name: params}, None, raw_tool_call_xml

    def _execute_tool(self, tool_name: str, params: Dict[str, str]) -> tuple[str, bool]:
        """Execute a tool with the given parameters and return the result and success status.

        Returns:
            tuple: (result, success)
                - result: The tool execution result or error message
                - success: True if execution was successful, False if there were errors
        """
        tool = self._get_tool_by_name(tool_name)
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

    @property
    def total_token_count(self) -> int:
        """Calculate the total number of words in the content of all messages."""
        return sum(len(message["content"].split()) for message in self.messages)

    def _truncate_context_window(self, verbosity=False):
        # Only pop messages (except system and last) until under token limit.
        while self.total_token_count > self.token_limit and len(self.messages) > 2:
            if verbosity:
                print(
                    f"==={self.total_token_count} > {self.token_limit}, removing oldest message (except system and last)==="
                )
            # Always preserve the first (system) and last message
            del self.messages[1]
        if verbosity:
            print(f"===CONTEXT WINDOW TOKEN COUNT: {self.total_token_count}===")

    async def run_stream(self, user_input: str) -> AsyncGenerator[ResponseEvent, None]:
        """Process a user message and yield responses (assistant messages and tool results).

        This method handles the conversation loop, including tool calls and user interactions.
        For the ask_followup_question tool, it yields a special response type that signals
        the main loop to get user input and then continue the conversation with that input.
        """
        self.messages.append({"role": "user", "content": user_input})
        continue_conversation = True

        while continue_conversation:
            self._truncate_context_window(verbosity=True)
            response = self.client.chat.completions.create(
                model=self.model, messages=self.messages, stream=True
            )

            full_response = ""
            tool_call, error_message, raw_tool_xml = (
                None,
                None,
                None,
            )  # Add raw_tool_xml
            halted = False
            tag_found = False
            thinking_found = False
            tool_found = False
            tokens_since_halted = 0
            halted_tokens = ""
            for chunk in response:
                if chunk.choices[0].delta.content:
                    full_content = chunk.choices[0].delta.content
                    parts = re.findall(r"(\s*\S+\s*|\s+)", full_content)
                    # print(f"CONTENT: '{full_content}' ===> PARTS: '{parts}'\n")
                    for content in parts:
                        full_response += content

                        if "<" in content:
                            halted = True

                        if halted:
                            tokens_since_halted += 1
                            halted_tokens += content

                            if tokens_since_halted > 5 and not tag_found:
                                halted = False
                                tokens_since_halted = 0
                                content = halted_tokens
                                tokens_since_halted = 0
                                yield ResponseEvent(
                                    type="response",
                                    content=halted_tokens,
                                )
                                halted_tokens = ""
                            elif (
                                "<tool_call>" in full_response
                                or "<thinking>" in full_response
                            ) and not tag_found:
                                tag_found = True

                            if tag_found:
                                if "</tool_call>" in full_response and not tool_found:
                                    tag_found = False
                                    (
                                        tool_call,
                                        error_message,
                                        raw_tool_xml,
                                    ) = self._parse_tool_call(full_response)

                                    if error_message:
                                        halted = False
                                        tokens_since_halted = 0
                                        halted_tokens = ""
                                        yield ResponseEvent(
                                            type="tool_error", content=error_message
                                        )
                                    if tool_call:
                                        tool_found = True
                                        halted = False
                                        tokens_since_halted = 0
                                        halted_tokens = ""
                                        yield ResponseEvent(
                                            type="tool_call",
                                            content=raw_tool_xml,  # Use raw XML here
                                        )

                                if (
                                    "</thinking>" in full_response
                                    and not thinking_found
                                ):
                                    tag_found = False
                                    thinking_found = True
                                    halted = False
                                    tokens_since_halted = 0
                                    yield ResponseEvent(
                                        type="thinking",
                                        content=halted_tokens,
                                    )
                                    halted_tokens = ""

                        else:
                            yield ResponseEvent(
                                type="response",
                                content=(
                                    f"<response>{content}</response>"
                                    if self.wrap_response_chunks
                                    else content
                                ),
                            )

            if full_response.strip() and not re.search(r"</[^>]+>\s*$", full_response):
                yield ResponseEvent(type="response", content="\n")

            if full_response and full_response.strip():
                self.messages.append({"role": "response", "content": full_response})
            else:
                continue_conversation = False
                continue

            if error_message:
                feedback = f"Tool call error: {error_message}\n\nPlease try again with the correct format."
                yield ResponseEvent(type="tool_error", content=feedback)
                self.messages.append({"role": "user", "content": feedback})
                continue_conversation = True

            elif tool_call:
                tool_name = list(tool_call.keys())[0]
                tool_params = tool_call[tool_name]

                tool_result, success = self._execute_tool(tool_name, tool_params)

                if success:
                    yield ResponseEvent(type="tool_response", content=tool_result)
                else:
                    yield ResponseEvent(type="tool_error", content=tool_result)

                history_message = f"<tool_response>\n{tool_result}\n</tool_response>"
                if not success:
                    tool = self._get_tool_by_name(tool_name)
                    if tool:
                        param_info = "\n".join(
                            [
                                f"- {name}: {config.get('description', '')} ({'required' if config.get('required') else 'optional'}, type: {config.get('type', 'string')})"
                                for name, config in tool.parameters.items()
                            ]
                        )
                        hint = f"\nPlease try again with the correct parameters for {tool_name}:\n{param_info}"
                        history_message += f"\n\n{hint}"

                self.messages.append({"role": "user", "content": history_message})

                continue_conversation = True

            else:
                continue_conversation = False

    def _get_tool_by_name(self, tool_name: str) -> Optional[Tool]:
        """Return the tool with the given name from self.tools, or None if not found."""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None
