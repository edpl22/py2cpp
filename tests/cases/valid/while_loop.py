def factorial(n: int) -> int:
    result: int = 1
    i: int = 1
    while i <= n:
        result = result * i
        i = i + 1
    return result


print(factorial(0))
print(factorial(1))
print(factorial(6))
