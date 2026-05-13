"""A compiler for GRPlugin layouts"""


class MapbuilderException(Exception):
    def __init__(self, message, file=None, item=None):
        super().__init__(message)
        self.file = file
        self.item = item

