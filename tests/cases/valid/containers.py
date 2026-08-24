def first(nums: list[int]) -> int:
    return nums[0]


nums: list[int] = [1, 2, 3, 4, 5]
print(nums)
print(nums[0])
print(nums[-1])
print(first(nums))

names: list[str] = ["a", "b", "c"]
print(names)

flags: list[bool] = [1 > 0, 0 > 1, 2 > 1]
print(flags)

squares: list[int] = [x * x for x in range(5)]
print(squares)

above_two: list[int] = [x for x in nums if x > 2]
print(above_two)

doubled: list[int] = [x * 2 for x in nums]
print(doubled)

ages: dict[str, int] = {"alice": 30, "bob": 25}
print(ages)
print(ages["alice"])

total: int = 0
for key in ages:
    total = total + ages[key]
print(total)

unique: set[int] = {1, 2, 2, 3, 3, 3}
print(unique)

count: int = 0
for value in unique:
    count = count + value
print(count)

point: tuple[int, int] = (3, 4)
print(point)
print(point[0])
print(point[-1])

single: tuple[int] = (7,)
print(single)

pair: tuple[int, str] = (1, "one")
print(pair)

nested: list[tuple[int, str]] = [(1, "a"), (2, "b")]
print(nested)

quoted: str = "quo'te"
print([quoted])
