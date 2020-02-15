from qzone import get_args, getFullContent
import qzone

with open("test.html", encoding='utf-8') as f: html = f.read()
cookie, gtk, qzonetoken = get_args()
qzone.headers["Cookie"] = cookie
html = getFullContent(html, gtk, qzonetoken)
print(html)