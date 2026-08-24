def safe_divide(a: int, b: int) -> int:
    result: int = 0
    try:
        result = a // b
    except ZeroDivisionError:
        print(f"cannot divide {a} by zero")
    return result


print(safe_divide(17, 5))
print(safe_divide(17, 0))
print(safe_divide(-17, 5))

inventory: dict[str, int] = {"apples": 12, "pears": 4}
requested: list[str] = ["apples", "pears", "kiwis"]

for item in requested:
    try:
        print(f"{item}: {inventory[item]}")
    except KeyError:
        print(f"{item}: out of stock")

try:
    raise ValueError("negative quantity")
except ValueError as e:
    print(f"rejected order: {e}")

try:
    raise KeyError("missing sku")
except LookupError:
    print("caught missing item via LookupError")

print("done")
