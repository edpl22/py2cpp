// Python-compatible `print`: space-separated arguments followed by a
// trailing newline, matching CPython's default sep=" ", end="\n".
//
// bool is special-cased to print "True"/"False" (Python's actual output)
// rather than C++'s default "1"/"0" -- streaming a bool through
// std::cout without std::boolalpha would otherwise silently produce text
// that doesn't match what the same Python program prints.
//
// Implemented as a variadic template so that supporting more argument
// types later (strings, f-strings, mixed values) only means adding a
// branch here, not reshaping every call site the backend already emits.
#pragma once

#include <iostream>
#include <type_traits>

namespace pyrt {

namespace detail {

inline void print_separated() {}

template <typename First, typename... Rest>
void print_separated(const First& first, const Rest&... rest) {
    if constexpr (std::is_same_v<std::decay_t<First>, bool>) {
        std::cout << (first ? "True" : "False");
    } else {
        std::cout << first;
    }
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
