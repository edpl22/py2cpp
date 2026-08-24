// Shared "how do we print/represent a value" dispatch, used both by
// pyrt::print (top-level output, see print.hpp) and by every container's
// own operator<< (element formatting, see list.hpp/dict.hpp/set.hpp).
//
// A bool always renders as True/False and a Str always renders quoted and
// escaped here -- top-level print() separately special-cases a *bare* Str
// argument to stay unquoted, which is the one place Python's str() and
// repr() of a value actually differ for the types this milestone
// supports; every other supported type's str() and repr() coincide.
//
// Every call site in this runtime reaches these through the qualified
// name 'pyrt::detail::write_repr', never a bare 'write_repr(...)' relying
// on argument-dependent lookup: ADL cannot find a pyrt::detail overload
// for e.g. std::tuple<std::int64_t> (whose only associated namespace is
// std, not pyrt), so every overload this dispatch might ever need --
// including the std::tuple one -- is declared together in this one file,
// included before anything that calls it (see pyrt.hpp's include order),
// so ordinary qualified lookup always finds the full overload set.
#pragma once

#include <cstddef>
#include <ostream>
#include <string>
#include <tuple>
#include <type_traits>
#include <utility>

#include "string.hpp"

namespace pyrt::detail {

inline void write_str_repr(std::ostream& os, const Str& s) {
    const std::string& bytes = s.raw();
    char quote = '\'';
    if (bytes.find('\'') != std::string::npos && bytes.find('"') == std::string::npos) {
        quote = '"';
    }
    os << quote;
    for (char c : bytes) {
        if (c == quote || c == '\\') {
            os << '\\' << c;
        } else if (c == '\n') {
            os << "\\n";
        } else if (c == '\t') {
            os << "\\t";
        } else if (c == '\r') {
            os << "\\r";
        } else {
            os << c;
        }
    }
    os << quote;
}

template <typename T>
void write_repr(std::ostream& os, const T& value) {
    if constexpr (std::is_same_v<T, bool>) {
        os << (value ? "True" : "False");
    } else if constexpr (std::is_same_v<T, Str>) {
        write_str_repr(os, value);
    } else {
        os << value;
    }
}

template <typename Tuple, std::size_t... I>
void write_tuple_elements(std::ostream& os, const Tuple& t, std::index_sequence<I...>) {
    std::size_t index = 0;
    ((os << (index++ == 0 ? "" : ", "), write_repr(os, std::get<I>(t))), ...);
}

// A single-element tuple prints with a trailing comma ('(1,)'), matching
// Python's own convention for disambiguating it from a parenthesized
// expression.
template <typename... Ts>
void write_repr(std::ostream& os, const std::tuple<Ts...>& t) {
    os << '(';
    write_tuple_elements(os, t, std::index_sequence_for<Ts...>{});
    if constexpr (sizeof...(Ts) == 1) {
        os << ',';
    }
    os << ')';
}

}  // namespace pyrt::detail
