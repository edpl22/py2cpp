// pyrt's own exception hierarchy (the M6 project-brief decision, "Decision
// E"): a curated, growing-on-demand subset of Python's builtin exception
// types, mirrored as a real single-inheritance C++ hierarchy rooted at
// PyException, exactly the same shape ir/lower.py's
// semantic/exceptions.py::EXCEPTION_HIERARCHY registry describes on the
// Python side.
//
// Every exception carries one message (Str), matching the common
// 'raise ValueError("message")' shape -- multi-arg '.args' is deferred.
// PyException derives std::exception so an uncaught one still terminates
// the program the same portable way every other uncaught C++ exception
// does (see operators.hpp's own history of this before this header
// existed): a nonzero exit code on every platform, even though *what*,
// if anything, lands on stderr is compiler/runtime-specific.
//
// pyrt::str(const PyException&) (declared here, not string.hpp, to avoid
// a circular header dependency) lets an 'except Foo as e:' binding be
// interpolated into an f-string the same way an int/bool value already
// is; operator<< lets it go straight to pyrt::print(e) or a container's
// own repr machinery, the same way pyrt::Str's own operator<< does.
#pragma once

#include <exception>
#include <ostream>
#include <utility>

#include "string.hpp"

namespace pyrt {

class PyException : public std::exception {
public:
    explicit PyException(Str message) : message_(std::move(message)) {}

    const char* what() const noexcept override { return message_.raw().c_str(); }
    const Str& message() const { return message_; }

private:
    Str message_;
};

inline std::ostream& operator<<(std::ostream& os, const PyException& e) {
    return os << e.message();
}

inline Str str(const PyException& e) {
    return e.message();
}

// clang-format off
class ValueError        : public PyException     { public: using PyException::PyException; };
class TypeError         : public PyException     { public: using PyException::PyException; };
class RuntimeError      : public PyException     { public: using PyException::PyException; };
class LookupError       : public PyException     { public: using PyException::PyException; };
class IndexError        : public LookupError     { public: using LookupError::LookupError; };
class KeyError          : public LookupError     { public: using LookupError::LookupError; };
class ArithmeticError   : public PyException     { public: using PyException::PyException; };
class ZeroDivisionError : public ArithmeticError { public: using ArithmeticError::ArithmeticError; };
class OverflowError     : public ArithmeticError { public: using ArithmeticError::ArithmeticError; };
// clang-format on

}  // namespace pyrt
