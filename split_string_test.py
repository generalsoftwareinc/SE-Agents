import re

# Split the string, grouping whitespace with adjacent words or matching whitespace blocks
text = " "  # Test case for whitespace-only string
# The pattern (\s*\S+\s*) matches a word with optional surrounding whitespace
# The pattern (\s+) matches one or more whitespace characters
parts = re.findall(r"(\s*\S+\s*|\s+)", text)

# Print each part, enclosed in single quotes for clarity
for part in parts:
    print(f"'{part}'")
