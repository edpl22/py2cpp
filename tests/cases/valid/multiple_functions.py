def square(x: int) -> int:
    return x * x


def sum_of_squares(a: int, b: int) -> int:
    return square(a) + square(b)


print(sum_of_squares(3, 4))
