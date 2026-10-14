"""Extract numeric instances verbatim from the public OR-Library collection."""

import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

SOURCE = "https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files/jobshop1.txt"
TARGET = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    raw = urlopen(SOURCE, timeout=60).read().decode("utf-8")
    TARGET.mkdir(exist_ok=True)
    sources = []
    for name in ("ft06", "ft10"):
        section = re.search(rf"instance\s+{name}\b(.*?)(?=\binstance\s|\Z)", raw, re.S)
        if section is None:
            raise RuntimeError(f"Missing benchmark: {name}")
        lines = section.group(1).splitlines()
        header = next(i for i, line in enumerate(lines) if re.fullmatch(r"\s*\d+\s+\d+\s*", line))
        jobs, _ = map(int, lines[header].split())
        data = "\n".join(line.strip() for line in lines[header : header + jobs + 1]) + "\n"
        (TARGET / f"{name}.txt").write_text(data, encoding="utf-8")
        sources.append({"name": name, "source": SOURCE, "sha256": hashlib.sha256(data.encode()).hexdigest()})
    (TARGET / "sources.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    print("Fetched and extracted: " + ", ".join(item["name"] for item in sources))


if __name__ == "__main__":
    main()
