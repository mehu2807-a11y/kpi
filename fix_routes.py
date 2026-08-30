import os
path = r'f:\Bussiness\app.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# Change the index route to redirect to /dashboard
replacement = """@app.route('/')
def index():
    return redirect(url_for('dashboard'))"""

import re
# Check if redirect, url_for is imported
if 'redirect' not in text:
    text = text.replace('from flask import Flask, render_template, request, jsonify', 'from flask import Flask, render_template, request, jsonify, redirect, url_for')

text = re.sub(r"@app\.route\('/'\)\s+def index\(\):\s+.*?return render_template\('index\.html'\)", replacement, text, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print("Route fixed.")
