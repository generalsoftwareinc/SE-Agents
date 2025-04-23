import re

# Split the string, grouping whitespace with adjacent words or matching whitespace blocks
text = " and that I always use thinking blocks before my responses.</thinking>I have reviewed"  # Test case provided by user
# The pattern (<|>|\s+|[^\s<>]+) matches '<', '>', whitespace, or sequences of non-delimiter characters
parts = re.findall(r"(<|>|\s+|[^\s<>]+)", text)

# Print each part, enclosed in single quotes for clarity
for part in parts:
    print(f"'{part}'")
