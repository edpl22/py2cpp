def total(nums: list[int]) -> int:
    result: int = 0
    for value in nums:
        result = result + value
    return result


scores: list[int] = [88, 95, 71, 60, 100]
print(scores)
print(f"top score: {scores[0]}, last score: {scores[-1]}")
print(f"sum: {total(scores)}")

passing: list[int] = [s for s in scores if s >= 70]
print(passing)

doubled: list[int] = [s * 2 for s in scores]
print(doubled)

grades: dict[str, int] = {"alice": 95, "bob": 71, "carol": 60}
print(grades)
print(f"alice's grade: {grades['alice']}")

class_total: int = 0
for student in grades:
    class_total = class_total + grades[student]
print(f"class total: {class_total}")

unique_scores: set[int] = {88, 95, 71, 60, 100, 95, 88}  # noqa: B033 -- duplicates are the point: sets dedup on construction
unique_total: int = 0
for value in unique_scores:
    unique_total = unique_total + value
print(f"unique scores sum to {unique_total}")

best: tuple[str, int] = ("alice", 95)
print(best)
print(f"winner: {best[0]} with {best[1]}")
