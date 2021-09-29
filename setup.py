from setuptools import find_packages, setup

with open('src/VERSION') as f:
    __version__ = f.read()

NAME = 'Qzone2TG'
NAME_LOWER = NAME.lower()
PACKAGES = find_packages(where='src')
PACKAGES += ['utils']

PACKAGES = [f"{NAME_LOWER}.{i}" for i in PACKAGES]

setup(
    name=NAME,
    version=__version__,
    description='Forward Qzone feeds to telegram',
    author='JamzumSum',
    author_email='zzzzss990315@gmail.com',
    url='https://github.com/JamzumSum/Qzone2TG',
    license="AGPL-3.0",
    python_requires=">=3.8",
    install_requires=[
        'python-telegram-bot',
        'lxml',
        'omegaconf',
        'keyring',
        "TencentLogin[captcha] @ git+https://github.com/JamzumSum/QQQR.git>=2.3.0b5",
        "QzEmoji @ git+https://github.com/JamzumSum/QzEmoji.git>=0.2",
    ],
    extras_require={
        'socks': ['python-telegram-bot[socks]'],
    },
    tests_require=['pytest'],
    packages=PACKAGES,
    package_dir={NAME_LOWER: "src"},
    include_package_data=True,
)
