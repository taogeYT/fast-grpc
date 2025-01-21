from pathlib import Path
from fast_grpc.utils import (
    protoc_compile,
    import_proto_file,
    message_to_pydantic,
    pydantic_to_message,
)
from pydantic import BaseModel


def test_import_proto_file():
    """Test proto file importing"""
    proto_file = Path("test_import.proto")
    proto_file.write_text(
        """
        syntax = "proto3";
        package test;

        message TestMessage {
            string name = 1;
            int32 value = 2;
        }

        service TestService {
            rpc TestMethod (TestMessage) returns (TestMessage);
        }
    """
    )

    try:
        protoc_compile(proto_file)
        pb2, pb2_grpc = import_proto_file(proto_file)

        # Test pb2 module
        assert hasattr(pb2, "TestMessage")
        msg = pb2.TestMessage(name="test", value=42)
        assert msg.name == "test"
        assert msg.value == 42

        # Test pb2_grpc module
        assert hasattr(pb2_grpc, "TestServiceServicer")
        assert hasattr(pb2_grpc, "TestServiceStub")
        assert hasattr(pb2_grpc, "add_TestServiceServicer_to_server")
        # message_to_dict(msg)

    finally:
        proto_file.unlink(missing_ok=True)
        (proto_file.parent / "test_import_pb2.py").unlink(missing_ok=True)
        (proto_file.parent / "test_import_pb2_grpc.py").unlink(missing_ok=True)


def test_pydantic_message_conversion():
    """Test conversion between pydantic models and protobuf messages"""
    proto_file = Path("test_conversion.proto")
    proto_file.write_text(
        """
        syntax = "proto3";
        package test;

        message UserMessage {
            string user_name = 1;
            int32 user_age = 2;
            repeated string tags = 3;
            map<string, string> metadata = 4;
        }
    """
    )

    try:
        protoc_compile(proto_file)
        pb2, _ = import_proto_file(proto_file)

        class UserModel(BaseModel):
            user_name: str
            user_age: int
            tags: list[str]
            metadata: dict[str, str]

        # Test protobuf message to pydantic model
        message = pb2.UserMessage(
            user_name="test_user",
            user_age=25,
            tags=["tag1", "tag2"],
            metadata={"key": "value"},
        )

        pydantic_user = message_to_pydantic(message, UserModel)
        assert isinstance(pydantic_user, UserModel)
        assert pydantic_user.user_name == "test_user"
        assert pydantic_user.user_age == 25
        assert pydantic_user.tags == ["tag1", "tag2"]
        assert pydantic_user.metadata == {"key": "value"}

        # Test pydantic model to protobuf message
        new_user = UserModel(
            user_name="new_user",
            user_age=30,
            tags=["tag3", "tag4"],
            metadata={"key2": "value2"},
        )

        proto_message = pydantic_to_message(new_user, pb2.UserMessage)
        assert isinstance(proto_message, pb2.UserMessage)
        assert proto_message.user_name == "new_user"
        assert proto_message.user_age == 30
        assert list(proto_message.tags) == ["tag3", "tag4"]
        assert dict(proto_message.metadata) == {"key2": "value2"}

        # Test round trip conversion
        round_trip_model = message_to_pydantic(
            pydantic_to_message(pydantic_user, pb2.UserMessage), UserModel
        )
        assert round_trip_model == pydantic_user

    finally:
        proto_file.unlink(missing_ok=True)
        (proto_file.parent / "test_conversion_pb2.py").unlink(missing_ok=True)
        (proto_file.parent / "test_conversion_pb2_grpc.py").unlink(missing_ok=True)


def test_pydantic_message_nested_conversion():
    """Test conversion with nested structures"""
    proto_file = Path("test_nested.proto")
    proto_file.write_text(
        """
        syntax = "proto3";
        package test;

        message Address {
            string street = 1;
            string city = 2;
        }

        message Person {
            string name = 1;
            int32 age = 2;
            Address address = 3;
            repeated Address previous_addresses = 4;
        }
    """
    )

    try:
        protoc_compile(proto_file)
        pb2, _ = import_proto_file(proto_file)

        class AddressModel(BaseModel):
            street: str
            city: str

        class PersonModel(BaseModel):
            name: str
            age: int
            address: AddressModel
            previous_addresses: list[AddressModel]

        # Create a protobuf message
        address = pb2.Address(street="123 Main St", city="Test City")
        prev_address = pb2.Address(street="456 Old St", city="Old City")
        person = pb2.Person(
            name="test_person",
            age=30,
            address=address,
            previous_addresses=[prev_address],
        )

        # Test conversion to pydantic
        pydantic_person = message_to_pydantic(person, PersonModel)
        assert isinstance(pydantic_person, PersonModel)
        assert isinstance(pydantic_person.address, AddressModel)
        assert pydantic_person.name == "test_person"
        assert pydantic_person.age == 30
        assert pydantic_person.address.street == "123 Main St"
        assert len(pydantic_person.previous_addresses) == 1
        assert pydantic_person.previous_addresses[0].city == "Old City"

        # Test conversion back to protobuf
        proto_person = pydantic_to_message(pydantic_person, pb2.Person)
        assert isinstance(proto_person, pb2.Person)
        assert proto_person.name == "test_person"
        assert proto_person.address.street == "123 Main St"
        assert len(proto_person.previous_addresses) == 1
        assert proto_person.previous_addresses[0].city == "Old City"

    finally:
        proto_file.unlink(missing_ok=True)
        (proto_file.parent / "test_nested_pb2.py").unlink(missing_ok=True)
        (proto_file.parent / "test_nested_pb2_grpc.py").unlink(missing_ok=True)
