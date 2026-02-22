"""Patch index.html: add models.js script tag before app.js."""
import pathlib

path = pathlib.Path(r"c:\Users\parag\Downloads\PANTHER\web\static\index.html")
content = path.read_text(encoding="utf-8")

old = '<script src="/static/js/app.js"></script>'
new = '<script src="/static/js/models.js"></script>\n    <script src="/static/js/app.js"></script>'

if old in content:
    content = content.replace(old, new, 1)
    path.write_text(content, encoding="utf-8")
    print("OK: models.js script tag added")
else:
    print("NOT FOUND:", repr(content[-500:]))
