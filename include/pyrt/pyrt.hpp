// pyrt: the header-only C++ runtime used by py2cpp-generated code.
//
// Every header here is self-contained and includable on its own; this
// umbrella header exists purely for convenience.
#pragma once

// Sibling-relative, not "pyrt/operators.hpp": a quoted include first
// resolves relative to the including file's own directory, so writing
// "pyrt/..." here would look for a nested pyrt/pyrt/ directory once
// --emit-runtime copies this file to <output>/pyrt/pyrt.hpp with no -I
// flag to fall back to. Plain sibling names resolve correctly both then
// and when this header is found via -I<repo>/include instead.
//
// Order matters here: repr.hpp declares every overload of
// pyrt::detail::write_repr (including the std::tuple one) that print.hpp,
// list.hpp, dict.hpp, and set.hpp all call by qualified name. A qualified
// dependent name inside a template is looked up once, at the template's
// own definition point -- not re-looked-up at each instantiation -- so
// repr.hpp must be included, in full, before any header whose templates
// call into it.
#include "operators.hpp"
#include "string.hpp"
#include "repr.hpp"
#include "print.hpp"
#include "list.hpp"
#include "dict.hpp"
#include "set.hpp"
