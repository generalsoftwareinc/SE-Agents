import os

from dotenv import load_dotenv

from agent import Agent
from tools import DuckDuckGoSearch, FireCrawlFetchPage

load_dotenv(override=True)


def main():
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

    # Example: set to False to omit default instructions, or provide a custom description string
    add_default_instructions = (
        True  # Change to False to omit tool_calling, rules, and objective
    )
    custom_description = None  # Or set to a string to override the default description

    agent = Agent(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model=model,
        tools=[DuckDuckGoSearch(), FireCrawlFetchPage(firecrawl_key)],
        description=custom_description,
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
        gen = agent.process_message(user_input)

        # Process responses from the generator
        try:
            while True:
                response = next(gen)

                if response.type == "assistant":
                    print(response.content, end="", flush=True)
                elif response.type == "thinking":
                    print(
                        f"{GRAY}{response.content}{RESET}",
                        end="",
                        flush=True,
                    )
                elif response.type == "tool_call":
                    print(f"\n\n{GREEN}🟡 {response.content}{RESET}\n")
                elif response.type == "tool_result":
                    print(f"\n\n{BLUE}🟢 Tool result:\n{response.content}{RESET}\n")
                elif response.type == "tool_error":
                    print(f"\n\n{RED}🔴 Tool error:\n{response.content}{RESET}\n")
        except StopIteration:
            # Generator is done
            pass


if __name__ == "__main__":
    main()
