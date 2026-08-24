class Animal:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.age: int = 0

    def speak(self) -> str:
        return "..."

    def describe(self) -> str:
        return self.name + " says " + self.speak()


class Dog(Animal):
    def __init__(self, name: str, age: int) -> None:
        super().__init__(name)
        self.age: int = age

    def speak(self) -> str:
        return "Woof"


class Cat(Animal):
    def __init__(self, name: str) -> None:
        super().__init__(name)

    def speak(self) -> str:
        return "Meow"


class Kennel:
    def __init__(self, resident: Animal) -> None:
        self.resident: Animal = resident

    def announce(self) -> str:
        return self.resident.describe()


def total_ages(a: Animal, b: Animal) -> int:
    return a.age + b.age


dog: Dog = Dog("Rex", 3)
cat: Cat = Cat("Whiskers")
print(dog.describe())
print(cat.describe())
print(dog.age)
print(cat.age)

generic: Animal = dog
print(generic.speak())
generic = cat
print(generic.speak())

print(total_ages(dog, cat))

kennel: Kennel = Kennel(dog)
print(kennel.announce())

same_kennel: Kennel = kennel
same_kennel.resident = cat
print(kennel.announce())
