def classify(n: int) -> int:
    result: int = 0
    if n < 0:
        result = -1
    elif n == 0:
        result = 0
    else:
        result = 1
    return result


for i in range(-2, 3):
    print(classify(i))
