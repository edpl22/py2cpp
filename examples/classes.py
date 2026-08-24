class Shape:
    def __init__(self, name: str) -> None:
        self.name: str = name

    def area(self) -> int:
        return 0

    def describe(self) -> str:
        return f"{self.name} has area {self.area()}"


class Square(Shape):
    def __init__(self, side: int) -> None:
        super().__init__("square")
        self.side: int = side

    def area(self) -> int:
        return self.side * self.side


class Rectangle(Shape):
    def __init__(self, width: int, height: int) -> None:
        super().__init__("rectangle")
        self.width: int = width
        self.height: int = height

    def area(self) -> int:
        return self.width * self.height


def largest_area(a: Shape, b: Shape) -> int:
    largest: int = b.area()
    if a.area() > b.area():
        largest = a.area()
    return largest


square: Square = Square(4)
rectangle: Rectangle = Rectangle(3, 5)
print(square.describe())
print(rectangle.describe())

biggest: int = largest_area(square, rectangle)
print(f"largest area: {biggest}")

shape: Shape = square
print(shape.describe())
shape = rectangle
print(shape.describe())
