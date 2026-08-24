// Python-compatible `print`: space-separated arguments followed by a
// trailing newline, matching CPython's default sep=" ", end="\n".
//
// Implemented as a variadic template now, even though this milestone only
// ever calls it with std::int64_t arguments, so that supporting more
// argument types later (strings, f-strings, mixed values) only means
// adding operator<< support, not reshaping every call site the backend
// already emits.
#pragma once

#include <iostream>

namespace pyrt {

namespace detail {

inline void print_separated() {}

template <typename First, typename... Rest>
void print_separated(const First& first, const Rest&... rest) {
    std::cout << first;
    if constexpr (sizeof...(rest) > 0) {
        std::cout << ' ';
        print_separated(rest...);
    }
}

}  // namespace detail

template <typename... Args>
void print(const Args&... args) {
    detail::print_separated(args...);
    std::cout << '\n';
}

}  // namespace pyrt
