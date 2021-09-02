NAME = 'Qzone2TG'
NAME_LOWER = NAME.lower()

__EPOCH__ = (2, 0, 0)
__PRERELEASE__ = ('beta', 5)
__POSTRELEASE__ = None
__DEV__ = None

__EPOCH_STR__ = '.'.join(str(i) for i in __EPOCH__)

__PRERELEASE_STR__ = __PRERELEASE__ and ''.join(i[0] for i in __PRERELEASE__[0].split()) \
    .lower() + str(__PRERELEASE__[1]) or ''

__POSTRELEASE_STR__ = ".post" + str(__POSTRELEASE__) if __POSTRELEASE__  is not None else ''    # yapf: disable

__DEV_STR__ = ".dev" + str(__DEV__) if __DEV__ is not None else ''


def version():
    return __EPOCH_STR__ + __PRERELEASE_STR__ + __POSTRELEASE_STR__ + __DEV_STR__


if __name__ == '__main__':
    print(version())
