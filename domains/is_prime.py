PROMPT = "Check if a number is prime. Return True if prime, False otherwise."

TEST_CASES = [
    (2, True),
    (3, True),
    (4, False),
    (5, True),
    (7, True),
    (10, False),
    (13, True),
    (17, True),
    (20, False),
    (25, False),
    (29, True),
    (30, False),
    (31, True),
    (37, True),
    (100, False),
    (101, True),
    (113, True),
    (1, False),
    (0, False),
    (-7, False),
]

OUTPUT_TRANSFORM = None
