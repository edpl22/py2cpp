class Animal:
    def __init__(self, name: str) -> None:
        self.name: str = name


class Dog(Animal):
    def __init__(self, name: str) -> None:
        self.age: int = 0
