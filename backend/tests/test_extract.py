import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))

from services.file_processor.dispatcher import extract


async def main():
    if len(sys.argv) < 2:
        print("Usage: python test_extract.py <file_path>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    file_bytes = path.read_bytes()
    result = await extract(file_bytes, path.name)

    print(f"Filename : {result.filename}")
    print(f"MIME type: {result.mime_type}")
    print(f"Content  :\n{result.content}")


asyncio.run(main())
