import os
from agent import Agent


def main():
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL")

    if not api_key:
        print("Error: OPENROUTER_API_KEY environment variable not set")
        return

    agent = Agent(api_key=api_key, model=model)

    print("🤖 Starting agent loop...")
    print("Type 'exit' to end the conversation\n")

    while True:
        user_input = input("\nUser: ")
        if user_input.lower() == "exit":
            break

        print("\nAssistant: ", end="")
        for response_type, content in agent.process_message(user_input):
            if response_type == "assistant":
                print(content, end="", flush=True)
            elif response_type == "tool":
                # Add spacing before and after non-empty tool results
                if content.strip():
                    # Add double newline before tool result and single newline after
                    print(f"\n\nTool result:\n{content}\n")
                    # Add a newline before the next assistant response
                    print("")


if __name__ == "__main__":
    main()
