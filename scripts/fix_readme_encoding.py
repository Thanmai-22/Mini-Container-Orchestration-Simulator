"""Fix mixed UTF-8 / Windows-1252 dash bytes in README; output clean UTF-8."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
readme = root / "README.md"
data = readme.read_bytes()

# UTF-8 em dash (U+2014) and en dash (U+2013)
data = data.replace(b"\xe2\x80\x94", b" - ")
data = data.replace(b"\xe2\x80\x93", b" - ")
# Windows-1252 en dash / "smart dash" single byte (often from Notepad / PowerShell)
data = data.replace(b"\x97", b" - ")

text = data.decode("utf-8").replace("\r\n", "\n")
readme.write_text(text, encoding="utf-8", newline="\n")
print("README.md: normalized dashes, saved as UTF-8")
