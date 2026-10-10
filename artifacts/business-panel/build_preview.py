"""Embed actual brand assets in a standalone, offline design-review HTML."""
import base64
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRONT = Path(r"C:\Users\kench\Desktop\flexdrivefront")

def data_url(mime, content):
    return "data:" + mime + ";base64," + base64.b64encode(content).decode("ascii")

fonts = []
for weight, name in ((400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold")):
    content = (FRONT / f"app/assets/fonts/NotoSansGeorgian-{name}.woff2").read_bytes()
    fonts.append("@font-face{font-family:'Noto Sans Georgian';font-style:normal;font-weight:" + str(weight) + ";font-display:swap;src:url('" + data_url("font/woff2", content) + "') format('woff2')}")

component = (FRONT / "app/components/icons/NewFlexdriveLogoHorizontal.vue").read_text(encoding="utf-8")
svg = re.search(r"<svg\b[\s\S]*?</svg>", component).group(0)
svg = re.sub(r'\s+:[\w-]+="[^"]*"', "", svg)
svg = re.sub(r"<title\b[^>]*>[\s\S]*?</title>", "<title>FlexDrive</title>", svg)
svg = svg.replace('class="new-flexdrive-logo-horizontal"', 'class="new-flexdrive-logo-horizontal" data-variant="on-dark"')
style = re.search(r"<style\b[^>]*>([\s\S]*?)</style>", component).group(1)
svg = svg.replace("</svg>", "<style>" + style + "</style></svg>")

tokens = (FRONT / "app/assets/css/design-system.css").read_text(encoding="utf-8")
template = (HERE / "prototype.template.html").read_text(encoding="utf-8")
html = template.replace("__FONTS__", "\n".join(fonts)).replace("__TOKENS__", tokens).replace("__LOGO__", data_url("image/svg+xml", svg.encode("utf-8")))
assert not re.search(r"__[A-Z]+__", html)
output = HERE / "FlexDrive Business Preview.html"
output.write_text(html, encoding="utf-8")
script = re.search(r"<script>([\s\S]*?)</script>", html).group(1)
(HERE / "preview-script.check.js").write_text(script, encoding="utf-8")
print(f"Created: {output}\nSize: {output.stat().st_size:,} bytes; embedded logo and four Georgian font weights")
