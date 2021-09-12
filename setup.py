# setup.py
#!/usr/bin/env python
from src.__version__ import version, NAME, NAME_LOWER
from setuptools import setup, find_packages

PACKAGES = find_packages(where='src')
PACKAGES += ['utils']

PACKAGES = [NAME_LOWER] + [f"{NAME_LOWER}.{i}" for i in PACKAGES]

setup(
    name=NAME,
    version=version(),
    description='Forward Qzone feeds to telegram',
    author='JamzumSum',
    author_email='zzzzss990315@gmail.com',
    url='https://github.com/JamzumSum/Qzone2TG',
    license="AGPL-3.0",
    python_requires=">=3.8",                                       # for f-string and := op
    install_requires=[
        'python-telegram-bot', 'lxml', 'omegaconf', 'keyring',
        "TencentLogin[captcha] @ git+https://github.com/JamzumSum/QQQR.git",
        "QzEmoji @ git+https://github.com/JamzumSum/QzEmoji.git"
    ],
    extras_require={
        'socks': ['python-telegram-bot[socks]'],
    },
    tests_require=['demjson'],
    packages=PACKAGES,
    package_dir={
        NAME_LOWER: "src",
    },
    include_package_data=True,
)
