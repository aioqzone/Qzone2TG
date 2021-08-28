import logging
import re

import yaml

logger = logging.getLogger(__name__)
faceurl = re.compile(r"http://qzonestyle.gtimg.cn/qzone/em/e(\d+\..*)")


class EmojiMgr:
    face_path = "misc/qq_face.yaml"
    emoji_path = "misc/emoji.yaml"
    singleton = None

    def __init__(self, face_path: str = None, emoji_path: str = None) -> None:
        if face_path: self.face_path = face_path
        if emoji_path: self.emoji_path = emoji_path
        self.loadEmoji()

    def loadEmoji(self):
        with open(self.face_path, encoding='utf-8') as f:
            self.face = yaml.safe_load(f)
        with open(self.emoji_path, encoding='utf-8') as f:
            self.emoji = yaml.safe_load(f)

    def transEmoji(self, name: str) -> str:
        if name.endswith(".png"):
            return self.face.get(name, "[/表情]")
        elif name.endswith(".gif"):
            if name in self.emoji:
                return self.emoji[name]
            else:
                logger.warning('new gif: ' + name)
                return "[/表情]"

    def __getitem__(self, name):
        return self.transEmoji(name)

    @classmethod
    def factory(cls, *args, **kwargs):
        if cls.singleton is None:
            cls.singleton = cls(*args, **kwargs)
        return cls.singleton


def url2unicode(src: str):
    m = faceurl.search(src)
    if m is None: return ""
    return EmojiMgr.factory().transEmoji(m.group(1))
