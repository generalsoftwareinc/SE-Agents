import os

from agent import Agent
from tools import DuckDuckGoSearch, FireCrawlFetchPage


def main(stream: bool = False):
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL")
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")

    if not api_key:
        print("Error: OPENROUTER_API_KEY environment variable not set")
        return

    agent = Agent(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model=model,
        tools=[DuckDuckGoSearch(), FireCrawlFetchPage(firecrawl_key)],
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
        gen = agent.process_message(user_input, stream=stream)

        # Process responses from the generator
        try:
            while True:
                response = next(gen)

                if response.role == "assistant":
                    print(response.content, end="", flush=True)
                elif response.role == "tool":
                    # Add spacing before and after non-empty tool results
                    if response.content.strip():
                        # Format the output based on whether it's an error message or normal result
                        if response.content.startswith(
                            "Tool call error:"
                        ) or response.content.startswith("Error:"):
                            print(f"\n\n🔴 {response.content}\n")
                        else:
                            print(f"\n\n🟢 Tool result:\n{response.content}\n")
                        # Add a newline before the next assistant response
                        print("")
                # We no longer need to handle ask_followup since we removed that tool
        except StopIteration:
            # Generator is done
            pass


if __name__ == "__main__":
    main(stream=True)
