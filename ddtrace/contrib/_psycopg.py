"""
The psycopg integration instruments the psycopg and psycopg2 libraries to trace Postgres queries.


Enabling
~~~~~~~~

The psycopg integration is enabled automatically when using
:ref:`ddtrace-run<ddtracerun>` or :ref:`import ddtrace.auto<ddtraceauto>`.

Or use :func:`patch()<ddtrace.patch>` to manually enable the integration::

    from ddtrace import patch
    patch(psycopg=True)


Global Configuration
~~~~~~~~~~~~~~~~~~~~

.. py:data:: ddtrace.config.psycopg["service"]

   The service name reported by default for psycopg spans.

   This option can also be set with the ``DD_PSYCOPG_SERVICE`` environment
   variable.

   Default: ``"postgres"``

.. py:data:: ddtrace.config.psycopg["trace_fetch_methods"]

   Whether or not to trace fetch methods.

   Can also configured via the ``DD_PSYCOPG_TRACE_FETCH_METHODS`` environment variable.

   Default: ``False``


.. py:data:: ddtrace.config.psycopg["trace_connect"]

   Whether or not to trace ``psycopg.connect`` method.

   Can also configured via the ``DD_PSYCOPG_TRACE_CONNECT`` environment variable.

   Default: ``False``


Instance Configuration
~~~~~~~~~~~~~~~~~~~~~~

To configure the psycopg integration on an per-connection basis use the
``Pin`` API::

    from ddtrace.trace import Pin
    import psycopg

    db = psycopg.connect(connection_factory=factory)
    # Use a pin to override the service name.
    Pin.override(db, service="postgres-users")

    cursor = db.cursor()
    cursor.execute("select * from users where id = 1")
"""
