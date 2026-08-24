def greet(name: str) -> str:
    return "hello, " + name


def shout(name: str) -> str:
    return name + "!!!"


print(greet("world"))
print(shout("py2cpp"))
print(f"shout: {shout('py2cpp')}")

n: int = 3
print(f"n = {n}, doubled = {n * 2}")

flag: bool = n > 1
print(f"flag = {flag}")

print("a" == "a")
print("a" == "b")
print("a" < "b")
print("apple" < "banana")
