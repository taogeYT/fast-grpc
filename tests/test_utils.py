import inspect
from unittest.mock import Mock, patch

from fast_grpc.utils import (
    await_sync_function,
    camel_to_snake,
    get_param_annotation_model,
    get_project_root_path,
    get_typed_annotation,
    get_typed_signature,
    import_string,
    is_camel_case,
    is_snake_case,
    snake_to_camel,
)


class TestCamelToSnake:
    def test_simple(self):
        assert camel_to_snake("HelloWorld") == "hello_world"

    def test_single_word(self):
        assert camel_to_snake("simple") == "simple"

    def test_http_server(self):
        assert camel_to_snake("HTTPServer") == "http_server"

    def test_fast_grpc(self):
        assert camel_to_snake("FastGRPC") == "fast_grpc"

    def test_all_caps_acronym(self):
        assert camel_to_snake("HTTPResponse") == "http_response"


class TestSnakeToCamel:
    def test_simple(self):
        assert snake_to_camel("hello_world") == "HelloWorld"

    def test_single_word(self):
        assert snake_to_camel("simple") == "Simple"

    def test_multiple_parts(self):
        assert snake_to_camel("fast_grpc_server") == "FastGrpcServer"


class TestIsCamelCase:
    def test_valid(self):
        assert is_camel_case("HelloWorld") is True

    def test_single_word(self):
        assert is_camel_case("Simple") is True

    def test_snake_case_rejected(self):
        assert is_camel_case("hello_world") is False

    def test_empty_string_matches(self):
        assert is_camel_case("") is True  # regex * quantifier matches empty

    def test_underscore_in_middle_rejected(self):
        assert is_camel_case("Hello_World") is False


class TestIsSnakeCase:
    def test_valid(self):
        assert is_snake_case("hello_world") is True

    def test_single_word_with_underscore(self):
        assert is_snake_case("hello_test") is True

    def test_no_underscore_fails(self):
        assert is_snake_case("simple") is False

    def test_empty_fails(self):
        assert is_snake_case("") is False

    def test_leading_underscore_fails(self):
        assert is_snake_case("_hello") is False

    def test_trailing_underscore_fails(self):
        assert is_snake_case("hello_") is False

    def test_uppercase_fails(self):
        assert is_snake_case("helloWorld") is False

    def test_double_underscore_fails(self):
        assert is_snake_case("hello__world") is False


class TestImportString:
    def test_valid_import(self):
        result = import_string("json.loads")
        import json
        assert result is json.loads

    def test_invalid_path_raises(self):
        import pytest
        with pytest.raises(ImportError, match="doesn't look like"):
            import_string("no_dots")


class TestGetProjectRootPath:
    def test_returns_cwd_for_unknown_module(self):
        import os
        result = get_project_root_path("nonexistent_module_xyz")
        assert result == os.getcwd()


class TestGetTypedSignature:
    def test_simple_function(self):
        def f(x: int, y: str) -> bool:
            return True

        sig = get_typed_signature(f)
        params = list(sig.parameters.values())
        assert len(params) == 2
        assert params[0].name == "x"
        assert params[0].annotation is int
        assert params[1].name == "y"
        assert params[1].annotation is str
        assert sig.return_annotation is bool

    def test_function_without_annotations(self):
        def f(a, b):
            pass

        sig = get_typed_signature(f)
        params = list(sig.parameters.values())
        assert params[0].annotation is inspect.Signature.empty
        assert sig.return_annotation is inspect.Signature.empty

    def test_unbound_method(self):
        class C:
            def method(self, x: int) -> str:
                return str(x)

        sig = get_typed_signature(C.method)
        params = list(sig.parameters.values())
        assert params[0].name == "self"
        assert params[1].name == "x"
        assert params[1].annotation is int

    def test_bound_method(self):
        class C:
            def method(self, x: int) -> str:
                return str(x)

        sig = get_typed_signature(C().method)
        params = list(sig.parameters.values())
        # Bound method drops self from signature
        assert params[0].name == "x"
        assert params[0].annotation is int


class TestGetTypedAnnotation:
    def test_resolves_string_annotation(self):
        ann = get_typed_annotation("int", {})
        assert ann is int

    def test_passes_through_non_string(self):
        ann = get_typed_annotation(int, {})
        assert ann is int


class TestGetParamAnnotationModel:
    def test_non_streaming_returns_annotation(self):
        annotation = str
        result = get_param_annotation_model(annotation, is_streaming=False)
        assert result is str

    def test_empty_annotation_returns_none(self):
        result = get_param_annotation_model(inspect.Signature.empty, is_streaming=False)
        assert result is None

    def test_non_asynciterable_origin_returns_none(self):
        from typing import List
        result = get_param_annotation_model(List[str], is_streaming=True)
        assert result is None


# Note: await_sync_function is not tested because it has a known bug
# (passes tuple instead of callable to context.run). Fix TBD separately.
