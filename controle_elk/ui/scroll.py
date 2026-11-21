def update_scrollbar(scrollbar, first, last):
    scrollbar.set(first, last)
    if float(first) > 0 or float(last) < 1:
        scrollbar.grid()
    else:
        scrollbar.grid_remove()
