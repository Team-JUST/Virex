def bytes_to_unit(n):
    if n < 1024:
        return f"{n} B"
    elif n < 1024**2:
        val = n / 1024
        return f"{val:.1f} KB".rstrip("0").rstrip(".")
    elif n < 1024**3:
        val = n / 1024**2
        return f"{val:.1f} MB".rstrip("0").rstrip(".")
    else:
        val = n / 1024**3
        return f"{val:.1f} GB".rstrip("0").rstrip(".")