PROMPT = "Given a string containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid (parentheses are correctly matched and nested). Return True if valid, False otherwise."

TEST_CASES = [
    ("()", True),
    ("()[]{}", True),
    ("(]", False),
    ("([)]", False),
    ("{[]}", True),
    ("", True),
    ("(", False),
    (")", False),
    ("((()))", True),
    ("((()))[]{}", True),
    ("(((((((())))))))", True),
    ("(((((((()))))))))", False),
    ("[{()}]", True),
    ("[{({})}]", True),
    ("{[}]", False),
    ("{", False),
    ("}", False),
    ("(((((", False),
    ("{{{{", False),
    ("{{{{}}}}", True),
]

OUTPUT_TRANSFORM = None
