class Foo:
    def __init__(self, x: int) -> None:
        self.x: int = x


a: Foo = Foo(1)
b: Foo = Foo(2)
print(a == b)
