import os

from agent import Agent
from tools import DuckDuckGoSearch, FireCrawlFetchPage


def main():
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

    print(agent.messages[0]["content"])

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

                # Unpack the response
                response_type, content = response

                if response_type == "assistant":
                    print(content, end="", flush=True)
                elif response_type == "tool":
                    # Add spacing before and after non-empty tool results
                    if content.strip():
                        # Format the output based on whether it's an error message or normal result
                        if content.startswith("Tool call error:") or content.startswith(
                            "Error:"
                        ):
                            print(f"\n\n🔴 {content}\n")
                        else:
                            print(f"\n\n🟢 Tool result:\n{content}\n")
                        # Add a newline before the next assistant response
                        print("")
                # We no longer need to handle ask_followup since we removed that tool
        except StopIteration:
            # Generator is done
            pass


if __name__ == "__main__":
    main()
