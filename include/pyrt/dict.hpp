// pyrt::Dict<K, V>: Python's dict.
//
// Preserves insertion order, matching CPython's actual, language-
// guaranteed dict behavior (since 3.7), via a flat vector of pairs rather
// than a hash map -- lookup is O(n), which is acceptable given this
// project's priorities (semantic correctness far outranks performance;
// see the top-level design principles) and avoids imposing a hashability
// requirement on K that this milestone has no need for yet.
//
// shared_ptr-wrapped for the same aliasing reason as pyrt::List (see
// list.hpp); .at() throws pyrt::KeyError for a missing key (an earlier
// version of this file, before py2cpp had its own exception hierarchy,
// threw std::out_of_range instead -- 'except KeyError:' now actually
// catches this).
#pragma once

#include <cstdint>
#include <memory>
#include <ostream>
#include <utility>
#include <vector>

#include "exceptions.hpp"
#include "repr.hpp"

namespace pyrt {

template <typename K, typename V>
class Dict {
public:
    Dict() : data_(std::make_shared<std::vector<std::pair<K, V>>>()) {}
    explicit Dict(std::vector<std::pair<K, V>> items)
        : data_(std::make_shared<std::vector<std::pair<K, V>>>(std::move(items))) {}

    std::int64_t size() const { return static_cast<std::int64_t>(data_->size()); }

    const V& at(const K& key) const {
        for (const auto& entry : *data_) {
            if (entry.first == key) {
                return entry.second;
            }
        }
        throw KeyError("key not found");
    }

    // Iterates key/value pairs; the backend binds a Python 'for k in d'
    // loop variable to '.first' of each pair (see IRForEach in the
    // compiler), since Python dict iteration yields keys only.
    auto begin() const { return data_->begin(); }
    auto end() const { return data_->end(); }

    friend bool operator==(const Dict& lhs, const Dict& rhs) { return *lhs.data_ == *rhs.data_; }
    friend bool operator!=(const Dict& lhs, const Dict& rhs) { return !(lhs == rhs); }

    friend std::ostream& operator<<(std::ostream& os, const Dict& dict) {
        os << '{';
        bool first = true;
        for (const auto& entry : *dict.data_) {
            if (!first) {
                os << ", ";
            }
            first = false;
            detail::write_repr(os, entry.first);
            os << ": ";
            detail::write_repr(os, entry.second);
        }
        os << '}';
        return os;
    }

private:
    std::shared_ptr<std::vector<std::pair<K, V>>> data_;
};

}  // namespace pyrt
