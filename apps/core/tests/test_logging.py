"""Tests for RequestContextFilter — request/tenant enrichment of log records."""
import logging

from apps.core.logging import RequestContextFilter
from apps.core.request_context import reset_request_id, set_request_id
from apps.tenancy.context import set_current_tenant_id, reset_current_tenant_id


def _make_record():
    return logging.LogRecord(
        name="pms.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )


def test_filter_defaults_to_dash_when_unbound():
    """Outside any request/tenant context both attributes default to '-'."""
    record = _make_record()
    assert RequestContextFilter().filter(record) is True
    assert record.request_id == "-"
    assert record.tenant_id == "-"


def test_filter_reflects_active_context():
    """With a request id and tenant bound, the record carries both values."""
    req_token = set_request_id("req-abc")
    tenant_token = set_current_tenant_id("tenant-xyz")
    try:
        record = _make_record()
        assert RequestContextFilter().filter(record) is True
        assert record.request_id == "req-abc"
        assert record.tenant_id == "tenant-xyz"
    finally:
        reset_current_tenant_id(tenant_token)
        reset_request_id(req_token)
