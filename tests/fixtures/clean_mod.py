def mean(values):
    return sum(values) / len(values)


def span(seq, empty):
    return [] if empty else [seq[0], seq[-1]]
