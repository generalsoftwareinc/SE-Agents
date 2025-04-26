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
            tool_event_occurred = False
            async for event in self.agent.run_stream(next_input):
                yield event

                if event.type == "tool_call":
                    tool_event_occurred = True
                    tool_call_dict, error_msg, _ = self.agent._parse_tool_call(
                        event.content
                    )

                    if error_msg or not tool_call_dict:
                        error_content = f"<tool_error>\nRunner failed to parse agent's yielded tool_call XML: {error_msg or 'Parse failure'}\nRaw XML:\n{event.content}\n</tool_error>\n"
                        yield ResponseEvent(type="tool_error", content=error_content)
                        next_input = error_content
                        break

                    tool_name = next(iter(tool_call_dict))
                    params = tool_call_dict[tool_name]

                    result, success = await self.agent._execute_tool(tool_name, params)

                    if success:
                        next_input = f"<tool_response>\n{result}\n</tool_response>\n"
                        # Yield the tool_response event so it can be displayed
                        yield ResponseEvent(type="tool_response", content=next_input)
                    else:
                        next_input = f"<tool_error>\nTool execution failed: {result}\n</tool_error>\n"
                        yield ResponseEvent(type="tool_error", content=next_input)

                    break  # Still break to feed the response back to the agent

                elif event.type == "tool_error":
                    tool_event_occurred = True
                    next_input = event.content
                    break

            if not tool_event_occurred:
                break
