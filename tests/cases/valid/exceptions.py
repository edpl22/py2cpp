def safe_floordiv(a: int, b: int) -> int:
    result: int = -1
    try:
        result = a // b
    except ZeroDivisionError:
        print("division by zero")
    return result


print(safe_floordiv(7, 2))
print(safe_floordiv(-7, 2))
print(safe_floordiv(7, -2))
print(safe_floordiv(-7, -2))
print(safe_floordiv(7, 0))

nums: list[int] = [1, 2, 3]
try:
    print(nums[5])
except IndexError as e:
    print(e)

ages: dict[str, int] = {"alice": 30}
try:
    print(ages["bob"])
except KeyError:
    print("no such key")

try:
    raise ValueError("bad input")
except ValueError as e:
    print("caught:", e)

try:
    raise ValueError("wrapped")
except Exception as e:
    print("caught via Exception:", e)

try:
    raise KeyError("missing")
except LookupError:
    print("caught via LookupError base")


def reraiser() -> int:
    result: int = 0
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        print("logging and re-raising")
        raise
    return result


try:
    reraiser()
except RuntimeError as e:
    print("outer caught:", e)

try:
    print("no error here")
except ValueError:
    print("never")

try:
    print("multiple handlers")
except TypeError:
    print("never 1")
except ValueError:
    print("never 2")
except Exception:
    print("never 3")

print("done")
