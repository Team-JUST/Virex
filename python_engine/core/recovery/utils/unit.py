def _fmt1(x):
    s = f"{x:.1f}"
    s = s.rstrip("0").rstrip(".")
    return s

def bytes_to_unit(n):
    if n < 1024:
        return f"{n} B"
    elif n < 1024**2:
        return f"{_fmt1(n/1024)} KB"
    elif n < 1024**3:
        return f"{_fmt1(n/1024**2)} MB"
    else:
        return f"{_fmt1(n/1024**3)} GB"