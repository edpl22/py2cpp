def f() -> int:
    try:
        pass
    except (ValueError, TypeError):
        pass
    return 0
