#!/usr/bin/env python3
import supernotelib as sn
import base64
import json
import sys

# Check Scrap.note
notebook = sn.load_notebook("/supernote/data/hays.donald@gmail.com/Supernote/Note/Scrap.note")
print(f"=== Scrap.note - Pages: {len(notebook.pages)} ===\n")

page = notebook.pages[0]
recogn_text = page.get_recogn_text()

if recogn_text and recogn_text != 'None':
    decoded = base64.b64decode(recogn_text).decode('utf-8')
    data = json.loads(decoded)

    print("Full OCR data structure:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print("NO OCR DATA FOUND!")
