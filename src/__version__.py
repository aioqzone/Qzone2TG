NAME = 'QZone2TG'
NAME_LOWER = NAME.lower()

__EPOCH__ = (2, 0, 0)
__PRERELEASE__ = ('beta', 3)
__POSTRELEASE__ = None
__DEV__ = None

__EPOCH_STR__ = '.'.join(str(i) for i in __EPOCH__)

__PRERELEASE_STR__ = __PRERELEASE__[0][0].lower(
) + str(__PRERELEASE__[1]) if __PRERELEASE__ else ''

__POSTRELEASE_STR__ = ".post" + str(__POSTRELEASE__) if __POSTRELEASE__ else ''

__DEV_STR__ = ".dev" + str(__DEV__) if __DEV__ else ''


def version():
    return __EPOCH_STR__ + __PRERELEASE_STR__ + __POSTRELEASE_STR__ + __DEV_STR__
