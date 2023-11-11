from tylisten import hookdef


@hookdef
def is_uin_blocked(uin: int) -> bool:
    return False
