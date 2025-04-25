from typing import AsyncGenerator, Dict

from se_agents.agent import Agent
from se_agents.schemas import ResponseEvent


class Runner:
    def __init__(self, agent: Agent):
        self.agent = agent

    async def run(self, user_input: str) -> AsyncGenerator[ResponseEvent, None]:
        """
        Execute a query through the Agent, handle tool calls, and yield events:
          - response / thinking: tokens from the model
          - tool_call: when the Agent requests a tool
          - tool_response: after executing the tool
        """
        next_input = user_input
        while True:
            tool_called = False
            # Stream until the Agent requests a tool or finishes
            async for event in self.agent.run_stream(next_input):
                if event.type == "tool_call":
                    tool_called = True
                    yield event

                    # Parse the tool call XML
                    tool_call_dict, error_msg, _ = self.agent._parse_tool_call(
                        event.content
                    )
                    if error_msg or not tool_call_dict:
                        yield ResponseEvent(
                            type="tool_error",
                            content=error_msg or "Failed to parse tool call",
                        )
                        # send parse error back into agent loop via next_input
                        next_input = f"<tool_error>\n{error_msg or 'Failed to parse tool call'}\n</tool_error>\n"
                        break

                    tool_name = next(iter(tool_call_dict))
                    params = tool_call_dict[tool_name]

                    # Execute the tool
                    result, success = await self.agent._execute_tool(tool_name, params)
                    # Wrap result in the XML expected by the Agent
                    xml_response = f"<tool_response>\n{result}\n</tool_response>\n"
                    yield ResponseEvent(type="tool_response", content=xml_response)

                    # send tool response back into agent loop via next_input
                    next_input = xml_response
                    break
                else:
                    yield event

            # If no tool was called in this pass, the Agent is done
            if not tool_called:
                break
