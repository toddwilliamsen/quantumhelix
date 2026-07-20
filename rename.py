import os
import re

def replace_in_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        return

    # Replace Quantum Helix and Quantum Helix with Quantum Helix
    new_content = re.sub(r'Quantum Helix', 'Quantum Helix', content, flags=re.IGNORECASE)
    new_content = re.sub(r'Quantum Helix', 'quantum-helix', new_content)
    new_content = re.sub(r'quantum_helix', 'quantum_helix', new_content)
    
    # Capitalized versions
    new_content = re.sub(r'Quantum Helix', 'Quantum Helix', new_content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

for root, dirs, files in os.walk('.'):
    if '.git' in root or 'node_modules' in root or '.venv' in root or 'dist' in root:
        continue
    for file in files:
        if file.endswith(('.py', '.jsx', '.html', '.md', '.sh', '.json', '.txt')):
            replace_in_file(os.path.join(root, file))

