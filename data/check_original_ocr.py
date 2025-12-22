#!/usr/bin/env python3
import supernotelib as sn
import base64
import json
from pathlib import Path

# Check an old file that likely has original Supernote OCR
test_file = "/supernote/data/hays.donald@gmail.com/Supernote/Note/Personal/Finance 💰/Money flow thoughts 20241224_104900(1).note"

print(f"=== Checking {Path(test_file).name} ===\n")

try:
    nb = sn.load_notebook(test_file)
    print(f"Total pages: {len(nb.pages)}")

    for i in range(min(2, len(nb.pages))):
        page = nb.pages[i]
        recogn_text = page.get_recogn_text()

        if recogn_text and recogn_text != 'None' and len(recogn_text) > 50:
            print(f"\n=== PAGE {i} - ORIGINAL SUPERNOTE OCR ===")
            decoded = base64.b64decode(recogn_text).decode('utf-8')
            data = json.loads(decoded)

            # Print structure
            print(f"Top keys: {list(data.keys())}")
            print(f"Type: {data.get('type')}")
            print(f"Elements: {len(data.get('elements', []))}")

            for elem in data.get('elements', []):
                if elem.get('type') == 'Text':
                    words = elem.get('words', [])
                    print(f"\nText element with {len(words)} word entries")
                    print(f"First 3 words:")
                    for w in words[:3]:
                        print(f"  {w}")
                    break
            break
        else:
            print(f"Page {i}: No OCR data")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
