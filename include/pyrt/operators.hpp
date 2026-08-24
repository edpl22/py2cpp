// Overflow-checked arithmetic for Python's arbitrary-precision `int`.
//
// py2cpp represents Python `int` as std::int64_t (see the project's type
// mapping decisions). Native signed-integer overflow is undefined
// behavior in C++, and would silently produce a wrong answer even if it
// weren't -- neither is acceptable for a value Python guarantees never
// overflows. Every arithmetic operation the backend emits for `int`
// therefore routes through these helpers, which detect overflow before
// it happens and raise instead of wrapping.
//
// These are written in portable standard C++ (bounds checked before the
// operation, never relying on the operation itself to signal overflow)
// rather than compiler builtins such as __builtin_add_overflow, since
// py2cpp targets GCC, Clang, and MSVC without compiler-specific
// extensions.
//
// Overflow raises pyrt::OverflowError (an earlier version of this file,
// before py2cpp had its own exception hierarchy, threw std::overflow_error
// instead -- 'except OverflowError:' now actually catches this).
// floordiv() additionally raises pyrt::ZeroDivisionError for a zero
// divisor, implementing Python's floor (round-toward-negative-infinity)
// division semantics, which differ from C++'s own truncating '/' for
// operands of different signs (e.g. Python's -7 // 2 is -4, not -3).
#pragma once

#include <cstdint>
#include <limits>

#include "exceptions.hpp"

namespace pyrt {

inline std::int64_t add(std::int64_t lhs, std::int64_t rhs) {
    constexpr std::int64_t max_value = std::numeric_limits<std::int64_t>::max();
    constexpr std::int64_t min_value = std::numeric_limits<std::int64_t>::min();

    if (rhs > 0 && lhs > max_value - rhs) {
        throw OverflowError("int addition overflowed");
    }
    if (rhs < 0 && lhs < min_value - rhs) {
        throw OverflowError("int addition overflowed");
    }
    return lhs + rhs;
}

inline std::int64_t sub(std::int64_t lhs, std::int64_t rhs) {
    constexpr std::int64_t max_value = std::numeric_limits<std::int64_t>::max();
    constexpr std::int64_t min_value = std::numeric_limits<std::int64_t>::min();

    if (rhs < 0 && lhs > max_value + rhs) {
        throw OverflowError("int subtraction overflowed");
    }
    if (rhs > 0 && lhs < min_value + rhs) {
        throw OverflowError("int subtraction overflowed");
    }
    return lhs - rhs;
}

inline std::int64_t mul(std::int64_t lhs, std::int64_t rhs) {
    constexpr std::int64_t max_value = std::numeric_limits<std::int64_t>::max();
    constexpr std::int64_t min_value = std::numeric_limits<std::int64_t>::min();

    if (lhs == 0 || rhs == 0) {
        return 0;
    }

    if (lhs == min_value || rhs == min_value) {
        bool safe = (lhs == min_value && rhs == 1) || (rhs == min_value && lhs == 1);
        if (!safe) {
            throw OverflowError("int multiplication overflowed");
        }
        return min_value;
    }

    // Neither operand is min_value, so negating either is always safe,
    // which lets us check magnitudes with division before multiplying --
    // computing lhs * rhs directly first would already be the overflow
    // we are trying to detect, which is undefined behavior for signed
    // integers in C++.
    std::int64_t abs_lhs = lhs < 0 ? -lhs : lhs;
    std::int64_t abs_rhs = rhs < 0 ? -rhs : rhs;

    if (abs_lhs > max_value / abs_rhs) {
        throw OverflowError("int multiplication overflowed");
    }

    return lhs * rhs;
}

inline std::int64_t floordiv(std::int64_t lhs, std::int64_t rhs) {
    if (rhs == 0) {
        throw ZeroDivisionError("integer division or modulo by zero");
    }
    constexpr std::int64_t min_value = std::numeric_limits<std::int64_t>::min();
    if (lhs == min_value && rhs == -1) {
        throw OverflowError("int floor division overflowed");
    }
    std::int64_t quotient = lhs / rhs;
    std::int64_t remainder = lhs % rhs;
    if (remainder != 0 && ((remainder < 0) != (rhs < 0))) {
        --quotient;
    }
    return quotient;
}

}  // namespace pyrt
