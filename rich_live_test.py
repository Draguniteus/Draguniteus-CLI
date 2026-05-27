import sys
sys.path.insert(0, 'src')
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
import time

console = Console()
print("Test 1: Live should show growing text word by word")
print("--- Start ---")
with Live(console=console, refresh_per_second=10, transient=False) as live:
    for i in range(10):
        text = "Word " * (i + 1)
        live.update(Markdown(f"**{text}**"))
        time.sleep(0.1)
    time.sleep(0.5)
print("--- End ---")
print("If words appeared one by one above, Live streaming works")
print()

print("Test 2: Streaming token-like behavior")
print("--- Start ---")
tokens = ["Hello", " ", "world", "!", " ", "How", " ", "are", " ", "you", "?"]
with Live(console=console, refresh_per_second=10, transient=False) as live:
    accumulated = ""
    for token in tokens:
        accumulated += token
        live.update(Markdown(accumulated))
        time.sleep(0.1)
    time.sleep(0.5)
print("--- End ---")
print("If letters appeared progressively above, token streaming works")