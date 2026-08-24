def f() -> int:
    try:
        raise NotAnException("x")
    except Exception:
        pass
    return 0
