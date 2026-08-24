def greeting(name: str, times: int) -> str:
    message: str = "hello, " + name + "!"
    if times > 1:
        message = message + f" (x{times})"
    return message


def louder(text: str) -> str:
    return text + "!!!"


for count in range(1, 4):
    print(greeting("world", count))

print(louder("py2cpp"))

a: str = "apple"
b: str = "banana"
print(f"{a} < {b} is {a < b}")
print(a == "apple")
