# setup.py
#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='QZone2TG',
    version='1.1',
    description='Forward QZone feeds to telegram',
    author='JamzumSum',
    author_email='zzzzss990315@gmail.com',
    url='https://github.com/JamzumSum/Qzone2TG',
    python_requires=">=3.8",                       # for f-string and := op
    install_requires=[
        'python-telegram-bot[socks]',
        'selenium',
        'demjson',
        'lxml',
        'opencv-python',
    ],
    packages=find_packages(where='src'),
    package_dir={"": "src"},
    data_files={"": ['misc']},
)
