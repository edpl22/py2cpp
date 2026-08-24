def f(a: int, step: int) -> int:
    total: int = 0
    for i in range(0, a, step):
        total = total + i
    return total
