def f() -> int:
    ages: dict[str, int] = {"alice": 30}
    return ages[1]


print(f())
