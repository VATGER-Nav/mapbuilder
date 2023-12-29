class PlainTextHandler:
    def handle(self, item) -> str:
        with open(item, mode="r", encoding="iso-8859-1") as input:
            return input.read()