def f() -> int:
    try:
        raise ValueError("x")
    except ValueError as e:
        y = e
    return 0
