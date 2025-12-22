#!/usr/bin/env python3
import supernotelib as sn
import base64
import json

print("="*60)
print("ORIGINAL SUPERNOTE OCR (Money flow thoughts)")
print("="*60)
nb_orig = sn.load_notebook("/supernote/data/hays.donald@gmail.com/Supernote/Note/Personal/Finance 💰/Money flow thoughts 20241224_104900(1).note")
recogn_orig = nb_orig.pages[0].get_recogn_text()
data_orig = json.loads(base64.b64decode(recogn_orig).decode('utf-8'))
print(json.dumps(data_orig, indent=2, ensure_ascii=False)[:1500])

print("\n" + "="*60)
print("OUR ENHANCED OCR (Scrap.note)")
print("="*60)
nb_ours = sn.load_notebook("/supernote/data/hays.donald@gmail.com/Supernote/Note/Scrap.note")
recogn_ours = nb_ours.pages[0].get_recogn_text()
data_ours = json.loads(base64.b64decode(recogn_ours).decode('utf-8'))
print(json.dumps(data_ours, indent=2, ensure_ascii=False)[:1500])

print("\n" + "="*60)
print("KEY DIFFERENCES:")
print("="*60)

# Compare structure
print(f"Original keys: {list(data_orig.keys())}")
print(f"Our keys: {list(data_ours.keys())}")

orig_elements = data_orig.get('elements', [])
our_elements = data_ours.get('elements', [])

print(f"\nOriginal elements: {len(orig_elements)}")
print(f"Our elements: {len(our_elements)}")

for i, (orig, ours) in enumerate(zip(orig_elements, our_elements)):
    print(f"\nElement {i}:")
    print(f"  Original type: {orig.get('type')}")
    print(f"  Our type: {ours.get('type')}")
    if orig.get('type') == 'Text':
        print(f"  Original has label: {'label' in orig}")
        print(f"  Our has label: {'label' in ours}")
        print(f"  Original has words: {'words' in orig}")
        print(f"  Our has words: {'words' in ours}")
