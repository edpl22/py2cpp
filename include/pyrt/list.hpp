// pyrt::List<T>: Python's list.
//
// Wraps a shared_ptr<deque<T>> rather than storing the underlying
// container by value: per the project's container-aliasing decision,
// 'b = a' must alias the same underlying list ('b.append(x)' would be
// visible through 'a' too), which a plain member would get wrong (it
// copies on assignment). Mutation itself isn't part of this milestone's
// supported Python subset yet, but the storage shape is chosen now so a later
// milestone's mutation support doesn't require re-deriving every List
// consumer's ownership model.
//
// Indexing (.at()) supports Python's negative-index convention and
// throws std::out_of_range on an out-of-bounds index -- a documented
// placeholder for the real exception until py2cpp defines its own
// runtime exception hierarchy (a later milestone, once try/except is
// supported), matching the same approach already used by operators.hpp.
//
// Backed by std::deque<T>, not std::vector<T>: std::vector<bool> is a
// bit-packed specialization whose element access returns a proxy object
// rather than a real bool&, which would make List<bool>::at() return a
// dangling reference to a temporary (undefined behavior) and would also
// silently break element printing (the proxy's type isn't bool, so
// pyrt::detail::write_repr's bool branch would never match). std::deque
// has no such specialization for any T, so this sidesteps the issue for
// every element type uniformly rather than special-casing bool.
#pragma once

#include <cstdint>
#include <deque>
#include <memory>
#include <ostream>
#include <stdexcept>
#include <utility>

#include "repr.hpp"

namespace pyrt {

template <typename T>
class List {
public:
    List() : data_(std::make_shared<std::deque<T>>()) {}
    explicit List(std::deque<T> items)
        : data_(std::make_shared<std::deque<T>>(std::move(items))) {}

    std::int64_t size() const { return static_cast<std::int64_t>(data_->size()); }

    const T& at(std::int64_t index) const {
        std::int64_t len = size();
        std::int64_t resolved = index < 0 ? index + len : index;
        if (resolved < 0 || resolved >= len) {
            throw std::out_of_range("list index out of range");
        }
        return (*data_)[static_cast<std::size_t>(resolved)];
    }

    auto begin() const { return data_->begin(); }
    auto end() const { return data_->end(); }

    friend bool operator==(const List& lhs, const List& rhs) { return *lhs.data_ == *rhs.data_; }
    friend bool operator!=(const List& lhs, const List& rhs) { return !(lhs == rhs); }

    friend std::ostream& operator<<(std::ostream& os, const List& list) {
        os << '[';
        bool first = true;
        for (const auto& item : *list.data_) {
            if (!first) {
                os << ", ";
            }
            first = false;
            detail::write_repr(os, item);
        }
        os << ']';
        return os;
    }

private:
    std::shared_ptr<std::deque<T>> data_;
};

}  // namespace pyrt
