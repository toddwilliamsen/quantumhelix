import os
import re

def replace_in_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return

    # Replace http://localhost:8000 with empty string for relative URLs
    new_content = content.replace("http://localhost:8000", "")
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

for root, dirs, files in os.walk('frontend/src'):
    for file in files:
        if file.endswith(('.jsx', '.js')):
            replace_in_file(os.path.join(root, file))
