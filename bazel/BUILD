py_library(
    name = "portfolio_greeting_lib",
    srcs = ["portfolio_greeting.py"],
)

py_binary(
    name = "portfolio_greeting",
    srcs = ["portfolio_greeting.py"],
    deps = [":portfolio_greeting_lib"],
)

py_test(
    name = "portfolio_greeting_test",
    srcs = ["portfolio_greeting_test.py"],
    deps = [":portfolio_greeting_lib"],
)
