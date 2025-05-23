import avro
from avro.schema import Schema as AvroSchema

from ddtrace.ext import schema as SCHEMA_TAGS
from ddtrace.internal.datastreams import data_streams_processor
from ddtrace.internal.datastreams.schemas.schema_builder import SchemaBuilder
from ddtrace.internal.datastreams.schemas.schema_iterator import SchemaIterator
from ddtrace.trace import Span


class SchemaExtractor(SchemaIterator):
    SERIALIZATION = "serialization"
    DESERIALIZATION = "deserialization"
    AVRO = "avro"

    def __init__(self, schema: AvroSchema):
        self.schema = schema

    @staticmethod
    def extract_property(field: avro, schema_name: str, field_name: str, builder: SchemaBuilder, depth: int) -> int:
        array = False
        type_ = None
        format_ = None
        description = None
        ref = None
        enum_values = None
        field_type = field.type
        if field_type.type == "array":
            # Array Type, get type of first item in array
            array = True
            format_ = field_type.props["items"].type
        elif getattr(field_type, "type", "") == "union":
            # Union Type
            schemas = getattr(field_type, "schemas", [])
            if len(schemas) > 0:
                for i in range(len(schemas)):
                    if i == 0:
                        type_ = "union[" + SchemaExtractor.get_type(schemas[0])
                    else:
                        type_ += "," + SchemaExtractor.get_type(schemas[i])
                type_ += "]"
        elif getattr(field_type, "type", "") == "record":
            # Nested Record Type
            type_ = "object"
            ref = f"#/components/schemas/{field_type.name}"
            if not SchemaExtractor.extract_schema(field_type, builder, depth + 1):
                return False
        else:
            # Primitive type
            type_ = SchemaExtractor.get_type(field_type)
            if field_type == "bytes":
                format_ = "byte"
            elif field_type == "int":
                format_ = "int32"
            elif field_type == "long":
                format_ = "int64"
            elif field_type == "float":
                format_ = "float"
            elif field_type == "double":
                format_ = "double"
        return builder.add_property(schema_name, field_name, array, type_, description, ref, format_, enum_values)

    @staticmethod
    def extract_schema(schema: AvroSchema, builder: SchemaBuilder, depth: int) -> bool:
        depth += 1
        schema_name = schema.fullname
        if not builder.should_extract_schema(schema_name, depth):
            return False
        try:
            for field in schema.fields:
                if not SchemaExtractor.extract_property(field, schema_name, field.name, builder, depth):
                    return False
        except Exception:
            return False
        return True

    @staticmethod
    def extract_schemas(schema: AvroSchema) -> bool:
        return data_streams_processor().get_schema(schema.fullname, SchemaExtractor(schema))

    def iterate_over_schema(self, builder: SchemaBuilder):
        self.extract_schema(self.schema, builder, 0)

    @staticmethod
    def attach_schema_on_span(schema: AvroSchema, span: Span, operation: str):
        if schema is None or span is None:
            return

        span.set_tag(SCHEMA_TAGS.SCHEMA_TYPE, SchemaExtractor.AVRO)
        span.set_tag(SCHEMA_TAGS.SCHEMA_NAME, schema.fullname)
        span.set_tag(SCHEMA_TAGS.SCHEMA_OPERATION, operation)

        if not data_streams_processor().can_sample_schema(operation):
            return

        prio = span.context.sampling_priority
        if prio is None or prio <= 0:
            return

        weight = data_streams_processor().try_sample_schema(operation)
        if weight == 0:
            return

        schema_data = SchemaExtractor.extract_schemas(schema)

        span.set_tag(SCHEMA_TAGS.SCHEMA_DEFINITION, schema_data.definition)
        span.set_metric(SCHEMA_TAGS.SCHEMA_WEIGHT, weight)
        span.set_tag(SCHEMA_TAGS.SCHEMA_ID, schema_data.id)

    @staticmethod
    def get_type(type_: str) -> str:
        return {
            "string": "string",
            "int": "integer",
            "long": "integer",
            "float": "number",
            "double": "number",
            "boolean": "boolean",
            "null": "null",
            "bytes": "string",
            "record": "object",
            "enum": "string",
            "array": "array",
            "map": "object",
            "fixed": "string",
        }.get(type_.type, "string")
