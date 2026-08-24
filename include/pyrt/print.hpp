// Python-compatible `print`: space-separated arguments followed by a
// trailing newline, matching CPython's default sep=" ", end="\n".
//
// A bare Str argument streams unquoted (Python's str() of a str is
// itself); every other supported type -- bool, int, and every container
// -- goes through pyrt::detail::write_repr (see repr.hpp), since for
// those types Python's str() and repr() always coincide.
#pragma once

#include <iostream>
#include <type_traits>

#include "repr.hpp"
#include "string.hpp"

namespace pyrt {

namespace detail {

inline void print_separated() {}

template <typename First, typename... Rest>
void print_separated(const First& first, const Rest&... rest) {
    if constexpr (std::is_same_v<std::decay_t<First>, Str>) {
        std::cout << first;
    } else {
        write_repr(std::cout, first);
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
