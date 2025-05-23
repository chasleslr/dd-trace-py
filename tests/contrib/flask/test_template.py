import flask

from ddtrace.contrib.internal.flask.patch import flask_version
from ddtrace.contrib.internal.flask.patch import unpatch
from ddtrace.trace import Pin

from . import BaseFlaskTestCase


class FlaskTemplateTestCase(BaseFlaskTestCase):
    def test_patch(self):
        """
        When we patch Flask
            Then ``flask.render_template`` is patched
            Then ``flask.render_template_string`` is patched
            Then ``flask.templating._render`` is patched
        """
        # DEV: We call `patch` in `setUp`
        self.assert_is_wrapped(flask.render_template)
        self.assert_is_wrapped(flask.render_template_string)
        self.assert_is_wrapped(flask.templating._render)

    def test_unpatch(self):
        """
        When we unpatch Flask
            Then ``flask.render_template`` is unpatched
            Then ``flask.render_template_string`` is unpatched
            Then ``flask.templating._render`` is unpatched
        """
        unpatch()
        self.assert_is_not_wrapped(flask.render_template)
        self.assert_is_not_wrapped(flask.render_template_string)
        self.assert_is_not_wrapped(flask.templating._render)

    def test_render_template(self):
        """
        When we call a patched ``flask.render_template``
            We create the expected spans
        """
        with self.app.app_context():
            with self.app.test_request_context("/"):
                response = flask.render_template("test.html", world="world")
                self.assertEqual(response, "hello world")

        # 1 for calling `flask.render_template`
        # 1 for tearing down the request
        # 1 for tearing down the app context we created
        spans = self.get_spans()
        self.assertEqual(len(spans), 3)

        self.assertEqual(spans[0].service, "tests.contrib.flask")
        self.assertEqual(spans[0].name, "flask.render_template")
        resource = "tests.contrib.flask" if flask_version >= (2, 2, 0) else "test.html"
        self.assertEqual(spans[0].resource, resource)  # FIXME: should always be 'test.html'?
        self.assertEqual(
            set(spans[0].get_tags().keys()),
            set(["flask.template_name", "runtime-id", "_dd.p.tid", "_dd.p.dm", "component", "language"]),
        )
        self.assertEqual(spans[0].get_tag("flask.template_name"), resource)  # FIXME: should always be 'test.html'?
        self.assertEqual(spans[1].name, "flask.do_teardown_request")
        self.assertEqual(spans[2].name, "flask.do_teardown_appcontext")

    def test_render_template_pin_disabled(self):
        """
        When we call a patched ``flask.render_template``
            When the app's ``Pin`` is disabled
                We do not create any spans
        """
        pin = Pin.get_from(self.app)
        pin.tracer.enabled = False

        with self.app.app_context():
            with self.app.test_request_context("/"):
                response = flask.render_template("test.html", world="world")
                self.assertEqual(response, "hello world")

        self.assertEqual(len(self.get_spans()), 0)

    def test_render_template_string(self):
        """
        When we call a patched ``flask.render_template_string``
            We create the expected spans
        """
        with self.app.app_context():
            with self.app.test_request_context("/"):
                response = flask.render_template_string("hello {{world}}", world="world")
                self.assertEqual(response, "hello world")

        # 1 for calling `flask.render_template`
        # 1 for tearing down the request
        # 1 for tearing down the app context we created
        spans = self.get_spans()
        self.assertEqual(len(spans), 3)

        self.assertEqual(spans[0].service, "tests.contrib.flask")
        self.assertEqual(spans[0].name, "flask.render_template_string")
        resource = "tests.contrib.flask" if flask_version >= (2, 2, 0) else "<memory>"
        self.assertEqual(spans[0].resource, resource)  # FIXME: should always be '<memory>'?
        self.assertEqual(
            set(spans[0].get_tags().keys()),
            set(["flask.template_name", "runtime-id", "_dd.p.tid", "_dd.p.dm", "component", "language"]),
        )
        self.assertEqual(spans[0].get_tag("flask.template_name"), resource)  # FIXME: should always be '<memory>'?
        self.assertEqual(spans[1].name, "flask.do_teardown_request")
        self.assertEqual(spans[2].name, "flask.do_teardown_appcontext")

    def test_render_template_string_pin_disabled(self):
        """
        When we call a patched ``flask.render_template_string``
            When the app's ``Pin`` is disabled
                We do not create any spans
        """
        pin = Pin.get_from(self.app)
        pin.tracer.enabled = False

        with self.app.app_context():
            with self.app.test_request_context("/"):
                response = flask.render_template_string("hello {{world}}", world="world")
                self.assertEqual(response, "hello world")

        self.assertEqual(len(self.get_spans()), 0)
