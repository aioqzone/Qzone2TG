from pathlib import Path

with open(Path(__file__).with_name('VERSION')) as f:
    __version__ = f.read()

NAME = 'Qzone2TG'
