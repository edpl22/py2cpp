// pyrt::Set<T>: Python's set.
//
// Insertion-ordered and deduplicates by '==' on construction. CPython's
// own set iteration order is hash-based and NOT part of the language's
// guaranteed semantics -- depending on it to compare generated-C++ output
// against CPython's output byte-for-byte would be unsound (the two are
// free to differ even though both are "correct" per the language spec).
// py2cpp's set therefore commits to a stronger, py2cpp-specific
// guarantee -- insertion order -- instead of attempting to reproduce
// CPython's actual, unspecified order; program behavior that depends on
// iterating a set is deterministic under py2cpp, just not necessarily
// identical to a given CPython build's iteration order.
//
// shared_ptr-wrapped for the same aliasing reason as pyrt::List (see
// list.hpp). Backed by std::deque<T> rather than std::vector<T> for the
// same reason as pyrt::List: std::vector<bool>'s bit-packed specialization
// returns a proxy object instead of a real bool& from element access,
// which std::deque never does for any T.
#pragma once

#include <cstdint>
#include <deque>
#include <memory>
#include <ostream>
#include <utility>

#include "repr.hpp"

namespace pyrt {

template <typename T>
class Set {
public:
    Set() : data_(std::make_shared<std::deque<T>>()) {}

    explicit Set(std::deque<T> items) : data_(std::make_shared<std::deque<T>>()) {
        for (auto& item : items) {
            bool seen = false;
            for (const auto& existing : *data_) {
                if (existing == item) {
                    seen = true;
                    break;
                }
            }
            if (!seen) {
                data_->push_back(std::move(item));
            }
        }
    }

    std::int64_t size() const { return static_cast<std::int64_t>(data_->size()); }

    bool contains(const T& value) const {
        for (const auto& item : *data_) {
            if (item == value) {
                return true;
            }
        }
        return false;
    }

    auto begin() const { return data_->begin(); }
    auto end() const { return data_->end(); }

    // Set equality is order-independent (unlike '==' on the underlying
    // deque, which py2cpp deliberately does not use here): two sets are
    // equal iff they contain the same elements, regardless of insertion
    // order, matching Python's actual set semantics.
    friend bool operator==(const Set& lhs, const Set& rhs) {
        if (lhs.size() != rhs.size()) {
            return false;
        }
        for (const auto& item : *lhs.data_) {
            if (!rhs.contains(item)) {
                return false;
            }
        }
        return true;
    }
    friend bool operator!=(const Set& lhs, const Set& rhs) { return !(lhs == rhs); }

    friend std::ostream& operator<<(std::ostream& os, const Set& set) {
        os << '{';
        bool first = true;
        for (const auto& item : *set.data_) {
            if (!first) {
                os << ", ";
            }
            first = false;
            detail::write_repr(os, item);
        }
        os << '}';
        return os;
    }

private:
    std::shared_ptr<std::deque<T>> data_;
};

}  // namespace pyrt
