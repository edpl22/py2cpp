// pyrt::Str: Python-compatible string values.
//
// Per the project's Unicode policy decision, Str stores its text as UTF-8
// bytes and, for this milestone, only supports whole-string operations
// (construction, concatenation, comparison, streaming) -- codepoint-aware
// indexing/length/iteration are introduced once a later milestone actually
// needs them, rather than being built ahead of demand.
//
// Comparison is implemented as plain byte-wise std::string comparison
// rather than decoding codepoints: for valid UTF-8, byte-lexicographic
// order and codepoint-lexicographic order are provably identical, so this
// is both correct and free.
#pragma once

#include <cstdint>
#include <ostream>
#include <string>
#include <utility>

namespace pyrt {

class Str {
public:
    Str() = default;
    Str(const char* text) : value_(text) {}
    explicit Str(std::string text) : value_(std::move(text)) {}

    friend Str operator+(const Str& lhs, const Str& rhs) { return Str(lhs.value_ + rhs.value_); }

    friend bool operator==(const Str& lhs, const Str& rhs) { return lhs.value_ == rhs.value_; }
    friend bool operator!=(const Str& lhs, const Str& rhs) { return lhs.value_ != rhs.value_; }
    friend bool operator<(const Str& lhs, const Str& rhs) { return lhs.value_ < rhs.value_; }
    friend bool operator<=(const Str& lhs, const Str& rhs) { return lhs.value_ <= rhs.value_; }
    friend bool operator>(const Str& lhs, const Str& rhs) { return lhs.value_ > rhs.value_; }
    friend bool operator>=(const Str& lhs, const Str& rhs) { return lhs.value_ >= rhs.value_; }

    friend std::ostream& operator<<(std::ostream& os, const Str& s) { return os << s.value_; }

private:
    std::string value_;
};

// Python str() conversions used to embed non-string values into f-strings.
inline Str str(std::int64_t value) { return Str(std::to_string(value)); }
inline Str str(bool value) { return Str(value ? "True" : "False"); }

}  // namespace pyrt
