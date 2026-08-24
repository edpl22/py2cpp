"""Backend unit tests: hand-built IR in, exact C++ text out.

These never touch the parser or lowering pass -- see tests/unit/ir for
those. This is purely "does the emitter format this IR shape correctly".
"""

from __future__ import annotations

from pathlib import Path

from py2cpp.backend.emit_cpp import emit_module
from py2cpp.diagnostics import SourceLocation
from py2cpp.ir.nodes import (
    BinaryOp,
    IRAttribute,
    IRAttributeAccess,
    IRAttributeAssign,
    IRBinaryExpr,
    IRClassDef,
    IRConstruct,
    IRConstructor,
    IRDictLiteral,
    IRForEach,
    IRFunction,
    IRIndex,
    IRListCompRange,
    IRListLiteral,
    IRLiteral,
    IRMethod,
    IRMethodCall,
    IRModule,
    IRParameter,
    IRPrintStmt,
    IRReturn,
    IRStringLiteral,
    IRToStr,
    IRTupleIndex,
    IRTupleLiteral,
    IRVarRef,
)
from py2cpp.types.model import ClassType, DictType, IntType, ListType, StringType, TupleType

_LOCATION = SourceLocation(filename=Path("test.py"), line=1, column=1)


def test_emits_add_function_and_main() -> None:
    add_function = IRFunction(
        name="add",
        parameters=(IRParameter(name="a", type=IntType()), IRParameter(name="b", type=IntType())),
        return_type=IntType(),
        body=(
            IRReturn(
                value=IRBinaryExpr(
                    op=BinaryOp.ADD,
                    left=IRVarRef(name="a", type=IntType()),
                    right=IRVarRef(name="b", type=IntType()),
                    type=IntType(),
                ),
                location=_LOCATION,
            ),
        ),
        location=_LOCATION,
    )
    module = IRModule(
        classes=(),
        name="add",
        functions=(add_function,),
        main_body=(
            IRPrintStmt(
                args=(
                    IRBinaryExpr(
                        op=BinaryOp.ADD,
                        left=IRVarRef(name="a", type=IntType()),
                        right=IRVarRef(name="b", type=IntType()),
                        type=IntType(),
                    ),
                ),
                location=_LOCATION,
            ),
        ),
    )

    output = emit_module(module)

    assert output == (
        "#include <cstdint>\n"
        "#include <memory>\n"
        '#include "pyrt/pyrt.hpp"\n'
        "\n"
        "std::int64_t add(std::int64_t a, std::int64_t b) {\n"
        "    return pyrt::add(a, b);\n"
        "}\n"
        "\n"
        "int main() {\n"
        "    pyrt::print(pyrt::add(a, b));\n"
        "    return 0;\n"
        "}\n"
    )


def test_keyword_parameter_name_is_escaped() -> None:
    function = IRFunction(
        name="identity",
        parameters=(IRParameter(name="class", type=IntType()),),
        return_type=IntType(),
        body=(IRReturn(value=IRVarRef(name="class", type=IntType()), location=_LOCATION),),
        location=_LOCATION,
    )
    module = IRModule(classes=(), name="identity", functions=(function,), main_body=())

    output = emit_module(module)

    assert "std::int64_t identity(std::int64_t class_)" in output
    assert "return class_;" in output


def test_emits_string_literal_and_concatenation() -> None:
    function = IRFunction(
        name="greet",
        parameters=(IRParameter(name="name", type=StringType()),),
        return_type=StringType(),
        body=(
            IRReturn(
                value=IRBinaryExpr(
                    op=BinaryOp.ADD,
                    left=IRStringLiteral(value="hello, ", type=StringType()),
                    right=IRVarRef(name="name", type=StringType()),
                    type=StringType(),
                ),
                location=_LOCATION,
            ),
        ),
        location=_LOCATION,
    )
    module = IRModule(classes=(), name="greet", functions=(function,), main_body=())

    output = emit_module(module)

    assert "pyrt::Str greet(pyrt::Str name) {" in output
    assert 'return (pyrt::Str("hello, ") + name);' in output


def test_emits_to_str_conversion() -> None:
    function = IRFunction(
        name="describe",
        parameters=(IRParameter(name="n", type=IntType()),),
        return_type=StringType(),
        body=(
            IRReturn(
                value=IRToStr(operand=IRVarRef(name="n", type=IntType()), type=StringType()),
                location=_LOCATION,
            ),
        ),
        location=_LOCATION,
    )
    module = IRModule(classes=(), name="describe", functions=(function,), main_body=())

    output = emit_module(module)

    assert "return pyrt::str(n);" in output


def test_emits_list_literal_using_deque_storage() -> None:
    module = IRModule(
        classes=(),
        name="m",
        functions=(),
        main_body=(
            IRPrintStmt(
                args=(
                    IRListLiteral(
                        elements=(
                            IRLiteral(value=1, type=IntType()),
                            IRLiteral(value=2, type=IntType()),
                        ),
                        type=ListType(IntType()),
                    ),
                ),
                location=_LOCATION,
            ),
        ),
    )

    output = emit_module(module)

    assert "pyrt::List<std::int64_t>(std::deque<std::int64_t>{1, 2})" in output


def test_emits_dict_literal() -> None:
    module = IRModule(
        classes=(),
        name="m",
        functions=(),
        main_body=(
            IRPrintStmt(
                args=(
                    IRDictLiteral(
                        keys=(IRStringLiteral(value="a", type=StringType()),),
                        values=(IRLiteral(value=1, type=IntType()),),
                        type=DictType(StringType(), IntType()),
                    ),
                ),
                location=_LOCATION,
            ),
        ),
    )

    output = emit_module(module)

    expected = (
        "pyrt::Dict<pyrt::Str, std::int64_t>("
        'std::vector<std::pair<pyrt::Str, std::int64_t>>{{pyrt::Str("a"), 1}})'
    )
    assert expected in output


def test_emits_tuple_literal_and_get_indexing() -> None:
    tuple_type = TupleType((IntType(), StringType()))
    module = IRModule(
        classes=(),
        name="m",
        functions=(),
        main_body=(
            IRPrintStmt(
                args=(
                    IRTupleIndex(
                        tuple_expr=IRTupleLiteral(
                            elements=(
                                IRLiteral(value=1, type=IntType()),
                                IRStringLiteral(value="a", type=StringType()),
                            ),
                            type=tuple_type,
                        ),
                        index=1,
                        type=StringType(),
                    ),
                ),
                location=_LOCATION,
            ),
        ),
    )

    output = emit_module(module)

    assert "std::get<1>(std::tuple<std::int64_t, pyrt::Str>(1, pyrt::Str(\"a\")))" in output


def test_emits_list_index_as_at_call() -> None:
    module = IRModule(
        classes=(),
        name="m",
        functions=(),
        main_body=(
            IRPrintStmt(
                args=(
                    IRIndex(
                        container=IRVarRef(name="values", type=ListType(IntType())),
                        index=IRLiteral(value=0, type=IntType()),
                        type=IntType(),
                    ),
                ),
                location=_LOCATION,
            ),
        ),
    )

    output = emit_module(module)

    assert "values.at(0)" in output


def test_emits_for_each_over_dict_binds_first() -> None:
    module = IRModule(
        classes=(),
        name="m",
        functions=(),
        main_body=(
            IRForEach(
                var="k",
                var_type=StringType(),
                iterable=IRVarRef(name="ages", type=DictType(StringType(), IntType())),
                body=(
                    IRPrintStmt(
                        args=(IRVarRef(name="k", type=StringType()),), location=_LOCATION
                    ),
                ),
                location=_LOCATION,
            ),
        ),
    )

    output = emit_module(module)

    assert "for (const auto& __pyrt_pair : ages) {" in output
    assert "pyrt::Str k = __pyrt_pair.first;" in output


def test_emits_list_comp_range_as_iife() -> None:
    module = IRModule(
        classes=(),
        name="m",
        functions=(),
        main_body=(
            IRPrintStmt(
                args=(
                    IRListCompRange(
                        element=IRVarRef(name="x", type=IntType()),
                        var="x",
                        start=IRLiteral(value=0, type=IntType()),
                        stop=IRLiteral(value=5, type=IntType()),
                        step=1,
                        condition=None,
                        type=ListType(IntType()),
                    ),
                ),
                location=_LOCATION,
            ),
        ),
    )

    output = emit_module(module)

    assert "pyrt::List<std::int64_t>([&]() {" in output
    assert "__pyrt_result.push_back(x);" in output
    assert "return __pyrt_result;" in output


def _animal_class() -> IRClassDef:
    return IRClassDef(
        name="Animal",
        base=None,
        attributes=(IRAttribute(name="name", type=StringType()),),
        constructor=IRConstructor(
            parameters=(IRParameter(name="name", type=StringType()),),
            base_args=None,
            body=(
                IRAttributeAssign(
                    obj=IRVarRef(name="self", type=ClassType("Animal")),
                    attr="name",
                    value=IRVarRef(name="name", type=StringType()),
                    type=StringType(),
                    location=_LOCATION,
                ),
            ),
            location=_LOCATION,
        ),
        methods=(
            IRMethod(
                name="speak",
                parameters=(),
                return_type=StringType(),
                body=(
                    IRReturn(
                        value=IRStringLiteral(value="...", type=StringType()),
                        location=_LOCATION,
                    ),
                ),
                is_virtual=True,
                is_override=False,
                location=_LOCATION,
            ),
        ),
        needs_virtual_destructor=True,
        location=_LOCATION,
    )


def _dog_class() -> IRClassDef:
    return IRClassDef(
        name="Dog",
        base="Animal",
        attributes=(),
        constructor=IRConstructor(
            parameters=(IRParameter(name="name", type=StringType()),),
            base_args=(IRVarRef(name="name", type=StringType()),),
            body=(),
            location=_LOCATION,
        ),
        methods=(
            IRMethod(
                name="speak",
                parameters=(),
                return_type=StringType(),
                body=(
                    IRReturn(
                        value=IRStringLiteral(value="Woof", type=StringType()),
                        location=_LOCATION,
                    ),
                ),
                is_virtual=True,
                is_override=True,
                location=_LOCATION,
            ),
        ),
        needs_virtual_destructor=True,
        location=_LOCATION,
    )


def test_emits_class_with_attribute_and_virtual_method() -> None:
    module = IRModule(classes=(_animal_class(),), name="m", functions=(), main_body=())

    output = emit_module(module)

    assert "struct Animal;" in output
    assert "struct Animal {" in output
    assert "pyrt::Str name{};" in output
    assert "Animal(pyrt::Str name) {" in output
    assert "this->name = name;" in output
    assert "virtual pyrt::Str speak() {" in output
    assert "virtual ~Animal() = default;" in output


def test_emits_subclass_with_base_initializer_and_override() -> None:
    module = IRModule(
        classes=(_animal_class(), _dog_class()), name="m", functions=(), main_body=()
    )

    output = emit_module(module)

    assert "struct Dog : Animal {" in output
    assert "Dog(pyrt::Str name) : Animal(name) {" in output
    assert "pyrt::Str speak() override {" in output
    # The override must not also be redundantly marked 'virtual'.
    assert "virtual pyrt::Str speak() override" not in output


def test_emits_construction_as_make_shared() -> None:
    module = IRModule(
        classes=(_animal_class(),),
        name="m",
        functions=(),
        main_body=(
            IRPrintStmt(
                args=(
                    IRAttributeAccess(
                        obj=IRConstruct(
                            class_name="Animal",
                            args=(IRStringLiteral(value="Rex", type=StringType()),),
                            type=ClassType("Animal"),
                        ),
                        attr="name",
                        type=StringType(),
                    ),
                ),
                location=_LOCATION,
            ),
        ),
    )

    output = emit_module(module)

    assert 'std::make_shared<Animal>(pyrt::Str("Rex"))->name' in output


def test_emits_method_call_via_arrow() -> None:
    module = IRModule(
        classes=(_animal_class(),),
        name="m",
        functions=(),
        main_body=(
            IRPrintStmt(
                args=(
                    IRMethodCall(
                        obj=IRVarRef(name="a", type=ClassType("Animal")),
                        method="speak",
                        args=(),
                        type=StringType(),
                    ),
                ),
                location=_LOCATION,
            ),
        ),
    )

    output = emit_module(module)

    assert "pyrt::print(a->speak());" in output
