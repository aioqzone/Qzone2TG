class QzoneError(RuntimeError):
    def __init__(self, code: int, *args):
        self.code = int(code)
        RuntimeError.__init__(self, *args)
