from HTMLParser import HTMLParser
# from qzone import getFullContent, get_args, headers
import json, re

with open("test.html", encoding="utf-8") as f:
    psr = HTMLParser(f)
    r = psr.isLike()
    print(r)