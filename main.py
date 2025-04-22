import asyncio
import datetime
import os
import re
from email.mime import base

from dotenv import load_dotenv

from se_agents.agent import Agent
from se_agents.tools import ExaCrawl, ExaSearch, MockNumberTool

load_dotenv(override=True)


rules = """
1. Your knowledge is limited to the information available up to April 2024.
2. You must use your tools to access up-to-date information from the web and provide accurate information to aid the users research goals
4. You must ALWAYS use your tools to verify the information you provide. If you are unsure about something, you must use your tools to find the answer.
5. Write a well-formatted answer that's optimized for readability:
   - Separate your answer into logical sections using level 2 headers (##) for sections and bolding (**) for subsections.
   - Incorporate a variety of lists, headers, and text to make the answer visually appealing.
   - Never start your answer with a header.
   - Use lists, bullet points, and other enumeration devices only sparingly, preferring other formatting methods like headers. Only use lists when there is a clear enumeration to be made
   - Only use numbered lists when you need to rank items. Otherwise, use bullet points.
   - Never nest lists or mix ordered and unordered lists.
   - When comparing items, use a markdown table instead of a list.
   - Bold specific words for emphasis.
   - Use markdown code blocks for code snippets, including the language for syntax highlighting.
   - Wrap all math expressions in LaTeX using double dollar signs ($$). For example: $$x^4 = x - 3$$
   - You may include quotes in markdown to supplement the answer
6. Be concise in your answer. Skip any preamble and provide the answer directly

"""


async def main():
    GRAY = "\033[90m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    RED = "\033[91m"
    RESET = "\033[0m"

    api_key = os.getenv("OPENROUTER_API_KEY")
    # api_key = None
    # base_url = None
    model = os.getenv("OPENROUTER_MODEL")
    base_url = os.getenv("OPENROUTER_BASE_URL")
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
    exa_key = os.getenv("EXA_API_KEY")

    if not api_key:
        print("Error: OPENROUTER_API_KEY environment variable not set")
        return

    # Instantiate the mock tool
    # mock_tool = MockNumberTool()

    # Original agent initialization (commented out)
    agent = Agent(
        api_key=api_key,
        base_url=base_url,
        model=model,
        tools=[ExaSearch(exa_key), ExaCrawl(exa_key)],
        # initial_messages=[
        #     {
        #         "role": "user",
        #         "content": """You are a helpful assistant that can perform web searches and fetch pages using Firecrawl. You can also analyze files and provide insights.
        #         """,
        #     },
        # ],
        additional_context=f"Current system time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        verbose=True,
        rules=rules,
        add_default_rules=False,
    )

    # agent.messages.append(
    #     {
    #         "role": "user",
    #         "content": """You are a helpful assistant that can perform web searches and fetch pages using Firecrawl.
    #         """,
    #     },
    # )
    # # print(agent.messages[0]["content"])

    # Initialize the test agent
    # test_agent = Agent(
    #     name="Test MockTools Agent",
    #     api_key=api_key,
    #     base_url=base_url,
    #     model=model,
    #     tools=[mock_tool],  # Equip only with the mock tool
    #     verbose=True,
    #     additional_context=f"Test Agent - Current time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    #     rules="You are a test agent equipped with MockIntTool. Your goal is to test its functionality.",
    #     add_default_rules=False,
    # )

    # Reusing the original loop structure for the test agent
    print("🤖 Starting TEST agent loop...")
    print("Type 'exit' to end the conversation\n")

    while True:
        user_input = input(f"\nUser:")
        # user_input = input(f"\nUser ({test_agent.name}) ")  # Modified prompt
        if user_input.lower() == "exit":
            break

        print(f"\nAssistant: ", end="")  # Modified prompt
        # print(f"\nAssistant ({test_agent.name}): ", end="")  # Modified prompt
        
        async for response in agent.run_stream(user_input):
        # Create the generator using the test_agent
        # async for response in test_agent.run_stream(user_input):
            if response.type == "response":
                print(
                    response.content,
                    end="",
                    flush=True,
                )
            elif response.type == "thinking":
                print(
                    f"{GRAY}{response.content}{RESET}",
                    end="",
                    flush=True,
                )
            elif response.type == "tool_call":
                print(f"\n\n{GREEN}🟡 {response.content}{RESET}\n")
            elif response.type == "tool_response":
                print(f"\n\n{BLUE}🟢 Tool response:\n{response.content}{RESET}\n")
            elif response.type == "tool_error":
                print(f"\n\n{RED}🔴 Tool error:\n{response.content}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
