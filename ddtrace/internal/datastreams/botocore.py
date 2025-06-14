import base64
import json
from typing import Any  # noqa:F401
from urllib import parse

from ddtrace import config
from ddtrace.internal import core
from ddtrace.internal.datastreams.processor import DsmPathwayCodec
from ddtrace.internal.datastreams.utils import _calculate_byte_size
from ddtrace.internal.logger import get_logger


log = get_logger(__name__)


def get_queue_name(params):
    # type: (dict) -> str
    """
    :params: contains the params for the current botocore action

    Return the name of the queue given the params
    """
    queue_url = params["QueueUrl"]
    url = parse.urlparse(queue_url)
    return url.path.rsplit("/", 1)[-1]


def get_topic_arn(params):
    # type: (dict) -> str
    """
    :params: contains the params for the current botocore action

    Return the name of the topic given the params
    """
    sns_arn = params["TopicArn"]
    return sns_arn


def get_stream(params):
    # type: (dict) -> str
    """
    :params: contains the params for the current botocore action

    Return the name of the stream given the params
    """
    stream = params.get("StreamARN", params.get("StreamName", ""))
    return stream


def inject_context(trace_data, endpoint_service, dsm_identifier, message):
    # type: (dict, str, str, Any) -> None
    """
    :endpoint_service: the name  of the service (i.e. 'sns', 'sqs', 'kinesis')
    :dsm_identifier: the identifier for the topic/queue/stream/etc

    Set the data streams monitoring checkpoint and inject context to carrier
    """
    from . import data_streams_processor as processor

    path_type = "type:{}".format(endpoint_service)

    payload_size = None
    if endpoint_service == "sqs":
        payload_size = calculate_sqs_payload_size(message, trace_data)
    elif endpoint_service == "sns":
        payload_size = calculate_sns_payload_size(message, trace_data)
    elif endpoint_service == "kinesis":
        payload_size = calculate_kinesis_payload_size(message, trace_data)

    if not dsm_identifier:
        log.debug("pathway being generated with unrecognized service: ", dsm_identifier)
    ctx = processor().set_checkpoint(
        ["direction:out", "topic:{}".format(dsm_identifier), path_type], payload_size=payload_size
    )
    DsmPathwayCodec.encode(ctx, trace_data)


def calculate_sqs_payload_size(message, trace_data=None):
    payload_size = _calculate_byte_size(message.get("MessageBody", ""))
    payload_size += _calculate_byte_size(message.get("MessageAttributes", {}))
    if trace_data:
        # we should count datadog message attributes which aren't yet added to the message
        payload_size += _calculate_byte_size({"_datadog": {"DataType": "String", "StringValue": trace_data}})
    payload_size += _calculate_byte_size(message.get("MessageSystemAttributes", {}))
    payload_size += _calculate_byte_size(message.get("MessageGroupId", ""))
    return payload_size


def calculate_sns_payload_size(message, trace_data):
    payload_size = _calculate_byte_size(message.get("Message", ""))
    payload_size += _calculate_byte_size(message.get("MessageAttributes", {}))
    # we should count datadog message attributes which aren't yet added to the message
    payload_size += _calculate_byte_size({"_datadog": {"DataType": "Binary", "BinaryValue": trace_data}})
    payload_size += _calculate_byte_size(message.get("Subject", ""))
    payload_size += _calculate_byte_size(message.get("MessageGroupId", ""))
    return payload_size


def calculate_kinesis_payload_size(message, trace_data=None):
    payload_size = _calculate_byte_size(message.get("Data", ""))
    payload_size += _calculate_byte_size(message.get("ExplicitHashKey", ""))
    payload_size += _calculate_byte_size(message.get("PartitionKey", ""))
    # if we don't have trace context data its because we are receiving and its within the message
    if trace_data:
        # we should count datadog message attributes which aren't yet added to the message
        payload_size += _calculate_byte_size({"_datadog": trace_data})
    return payload_size


def handle_kinesis_produce(ctx, stream, dd_ctx_json, record, *args):
    if config._data_streams_enabled:
        if "_datadog" not in dd_ctx_json:
            dd_ctx_json["_datadog"] = {}
        if stream:  # If stream ARN / stream name isn't specified, we give up (it is not a required param)
            inject_context(dd_ctx_json["_datadog"], "kinesis", stream, record)


def handle_sqs_sns_produce(ctx, span, endpoint_service, trace_data, params, message=None):
    # if a message wasn't included, that means that the message is in the params object
    if not message:
        message = params
    dsm_identifier = None
    if endpoint_service == "sqs":
        dsm_identifier = get_queue_name(params)
    elif endpoint_service == "sns":
        dsm_identifier = get_topic_arn(params)
    inject_context(trace_data, endpoint_service, dsm_identifier, message)


def handle_sqs_prepare(params):
    if "MessageAttributeNames" not in params:
        params.update({"MessageAttributeNames": ["_datadog"]})
    elif "_datadog" not in params["MessageAttributeNames"]:
        params.update({"MessageAttributeNames": list(params["MessageAttributeNames"]) + ["_datadog"]})


def get_datastreams_context(message):
    """
    Formats we're aware of:
        - message.Body.MessageAttributes._datadog.Value.decode() (SQS)
        - message.MessageAttributes._datadog.StringValue (SNS -> SQS)
        - message.MessageAttributes._datadog.BinaryValue.decode() (SNS -> SQS, raw)
        - message.messageAttributes._datadog.stringValue (SQS -> lambda)
    """
    context_json = None
    message_body = message
    try:
        body = message.get("Body")
        if body:
            message_body = json.loads(body)
    except (ValueError, TypeError):
        log.debug("Unable to parse message body as JSON, treat as non-json")

    message_attributes = message_body.get("MessageAttributes") or message_body.get("messageAttributes")
    if not message_attributes:
        log.debug("DataStreams skipped message: %r", message)
        return None

    if "_datadog" not in message_attributes:
        log.debug("DataStreams skipped message: %r", message)
        return None

    datadog_attr = message_attributes["_datadog"]

    if message_body.get("Type") == "Notification":
        # This is potentially a DSM SNS notification
        if datadog_attr.get("Type") == "Binary":
            context_json = json.loads(base64.b64decode(datadog_attr["Value"]).decode())
    elif "StringValue" in datadog_attr:
        # The message originated from SQS
        context_json = json.loads(datadog_attr["StringValue"])
    elif "stringValue" in datadog_attr:
        # The message originated from Lambda
        context_json = json.loads(datadog_attr["stringValue"])
    elif "BinaryValue" in datadog_attr:
        # Raw message delivery
        context_json = json.loads(datadog_attr["BinaryValue"].decode())
    else:
        log.debug("DataStreams did not handle message: %r", message)

    return context_json


def handle_sqs_receive(_, params, result, *args):
    from . import data_streams_processor as processor

    queue_name = get_queue_name(params)

    for message in result.get("Messages", []):
        try:
            context_json = get_datastreams_context(message)
            payload_size = calculate_sqs_payload_size(message)
            ctx = DsmPathwayCodec.decode(context_json, processor())
            ctx.set_checkpoint(["direction:in", "topic:" + queue_name, "type:sqs"], payload_size=payload_size)
        except Exception:
            log.debug("Error receiving SQS message with data streams monitoring enabled", exc_info=True)


class StreamMetadataNotFound(Exception):
    pass


def record_data_streams_path_for_kinesis_stream(params, time_estimate, context_json, record):
    from . import data_streams_processor as processor

    stream = get_stream(params)

    if not stream:
        log.debug("Unable to determine StreamARN and/or StreamName for request with params: ", params)
        raise StreamMetadataNotFound()

    payload_size = calculate_kinesis_payload_size(record)
    ctx = DsmPathwayCodec.decode(context_json, processor())
    ctx.set_checkpoint(
        ["direction:in", "topic:" + stream, "type:kinesis"],
        edge_start_sec_override=time_estimate,
        pathway_start_sec_override=time_estimate,
        payload_size=payload_size,
    )


def handle_kinesis_receive(_, params, time_estimate, context_json, record, *args):
    try:
        record_data_streams_path_for_kinesis_stream(params, time_estimate, context_json, record)
    except Exception:
        log.warning("Failed to report data streams monitoring info for kinesis", exc_info=True)


if config._data_streams_enabled:
    core.on("botocore.kinesis.update_record", handle_kinesis_produce)
    core.on("botocore.sqs_sns.update_messages", handle_sqs_sns_produce)
    core.on("botocore.sqs.ReceiveMessage.pre", handle_sqs_prepare)
    core.on("botocore.sqs.ReceiveMessage.post", handle_sqs_receive)
    core.on("botocore.kinesis.GetRecords.post", handle_kinesis_receive)
