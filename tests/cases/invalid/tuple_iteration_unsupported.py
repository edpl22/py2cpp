def f() -> int:
    total: int = 0
    point: tuple[int, int] = (3, 4)
    for value in point:
        total = total + value
    return total


print(f())
