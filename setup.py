# setup.py
#!/usr/bin/env python

from setuptools import setup, find_packages, find_namespace_packages

NAME = 'QZone2TG'
LOWERCASE = NAME.lower()
PACKAGES = find_packages(where='src') + find_namespace_packages(include=['misc'])
PACKAGES = [LOWERCASE] + [f"{LOWERCASE}.{i}" for i in PACKAGES]

setup(
    name='QZone2TG',
    version='2.0.0b2',
    description='Forward QZone feeds to telegram',
    author='JamzumSum',
    author_email='zzzzss990315@gmail.com',
    url='https://github.com/JamzumSum/Qzone2TG',
    license="AGPL-3.0",
    python_requires=">=3.8",                                                                         # for f-string and := op
    install_requires=[
        'python-telegram-bot',
        'lxml',
        'omegaconf',
        "sqlite3",
        "TencentLogin @ git+https://github.com/JamzumSum/QQQR.git"
    ],
    extras_require={
        'socks': ['python-telegram-bot[socks]'],
    },
    packages=PACKAGES,
    package_dir={
        LOWERCASE: "src",
        f"{LOWERCASE}.misc": 'misc',
    },
    include_package_data=True,
)
