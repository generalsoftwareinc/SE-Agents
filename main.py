import asyncio
import datetime
import os
import re

from dotenv import load_dotenv

from se_agents.agent import Agent
from se_agents.tools import DuckDuckGoSearch, FireCrawlFetchPage

load_dotenv(override=True)


async def main():
    GRAY = "\033[90m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    RED = "\033[91m"
    RESET = "\033[0m"

    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL")
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")

    if not api_key:
        print("Error: OPENROUTER_API_KEY environment variable not set")
        return

    agent = Agent(
        api_key=api_key,
        model=model,
        tools=[DuckDuckGoSearch(), FireCrawlFetchPage(firecrawl_key)],
        # initial_messages=[
        #     {
        #         "role": "user",
        #         "content": """You are a helpful assistant that can perform web searches and fetch pages using Firecrawl. You can also analyze files and provide insights.
        #         """,
        #     },
        # ],
        additional_context=f"Current system time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        wrap_response_chunks=True,
    )

    agent.messages.append(
        {
            "role": "user",
            "content": """You are a helpful assistant that can perform web searches and fetch pages using Firecrawl.
            """,
        },
    )

    # print(agent.messages[0]["content"])

    print("🤖 Starting agent loop...")
    print("Type 'exit' to end the conversation\n")

    while True:
        user_input = input("\nUser: ")
        if user_input.lower() == "exit":
            break

        print("\nAssistant: ", end="")
        # Create the generator
        async for response in agent.run_stream(user_input):
            if response.type == "response":
                content = re.search(
                    r"<response>(.*?)</response>", response.content, re.DOTALL
                )
                print(
                    content.group(1) if content else response.content,
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
