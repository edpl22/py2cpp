def count_positive(a: int, b: int, c: int) -> int:
    count: int = 0
    count = count + (a > 0)
    count = count + (b > 0)
    count = count + (c > 0)
    return count


def in_range(x: int, low: int, high: int) -> bool:
    return low <= x and x <= high


print(count_positive(1, -1, 5))
print(in_range(5, 0, 10))
print(in_range(15, 0, 10))
print(not in_range(15, 0, 10))
