# setup.py
#!/usr/bin/env python
from src.__version__ import version, NAME, NAME_LOWER
from setuptools import setup, find_packages, find_namespace_packages

PACKAGES = find_packages(where='src') + \
    find_namespace_packages(where='src', include=['utils', 'frontend']) + \
    find_namespace_packages(include=['misc'])

PACKAGES = [NAME_LOWER] + [f"{NAME_LOWER}.{i}" for i in PACKAGES]

setup(
    name=NAME,
    version=version(),
    description='Forward QZone feeds to telegram',
    author='JamzumSum',
    author_email='zzzzss990315@gmail.com',
    url='https://github.com/JamzumSum/Qzone2TG',
    license="AGPL-3.0",
    python_requires=">=3.8",                                       # for f-string and := op
    install_requires=[
        'python-telegram-bot', 'lxml', 'omegaconf',
        "TencentLogin @ git+https://github.com/JamzumSum/QQQR.git"
    ],
    extras_require={
        'socks': ['python-telegram-bot[socks]'],
    },
    packages=PACKAGES,
    package_dir={
        NAME_LOWER: "src",
        f"{NAME_LOWER}.misc": 'misc',
    },
    include_package_data=True,
)
