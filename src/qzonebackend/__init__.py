class QzoneError(RuntimeError):
    msg = 'unknown'

    def __init__(self, code: int, *args):
        self.code = int(code)
        if len(args) > 0 and isinstance(args[0], str):
            self.msg = args[0]
        RuntimeError.__init__(self, *args)

    def __str__(self) -> str:
        return f"Code {self.code}: {self.msg}"
