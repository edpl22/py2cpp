class Foo:
    def __init__(self, cond: bool) -> None:
        if cond:
            self.x: int = 1
        else:
            self.x: int = 2
