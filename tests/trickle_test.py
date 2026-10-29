"""A server that trickles its reply can't keep a request (and the sync lock)
past the deadline (HANCORE, marketplace #13263).

Each test runs a local server on 127.0.0.1 that sends a byte at a time, well
inside the socket timeout, and checks the request gives up on time.
"""

import os
import socketserver
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from omcal import auth, caldav, files, sync  # noqa: E402


class Trickle(socketserver.BaseRequestHandler):
    head = b""       # sent at once
    drip = b""       # then a byte every `gap` seconds
    gap = 0.05

    def handle(self):
        try:
            self.request.sendall(self.head)
            for b in self.drip:
                time.sleep(self.gap)
                self.request.sendall(bytes([b]))
        except OSError:
            pass   # the client gave up, as it should


def serve(head, drip, gap=0.05):
    handler = type("H", (Trickle,), {"head": head, "drip": drip, "gap": gap})
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d/" % srv.server_address[1]


class TrickleTest(unittest.TestCase):
    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_a_trickled_body_stops_at_the_deadline(self):
        # 2000 bytes at 20 a second would take 100 s; each byte comes well
        # inside the 30 s socket timeout, so only the deadline can stop it.
        self.srv, url = serve(b"HTTP/1.1 200 OK\r\nContent-Length: 2000\r\n\r\n", b"x" * 2000)
        start = time.monotonic()
        with urllib.request.urlopen(url, timeout=30) as r:
            with self.assertRaises(files.ReplyTooLarge):
                files.read_reply(r, deadline=1)
            self.assertLess(time.monotonic() - start, 2.5)

    def test_trickled_headers_stop_at_the_deadline(self):
        self.srv, url = serve(b"HTTP/1.1 200 OK\r\n", b"X-Slow: " + b"y" * 2000)
        get = files.within_deadline(lambda: urllib.request.urlopen(url, timeout=30).read(), seconds=1)
        start = time.monotonic()
        with self.assertRaises(OSError):   # ReplyTooLarge, or urllib's URLError around it
            get()
        self.assertLess(time.monotonic() - start, 2.5)

    def test_an_error_body_is_read_only_to_its_start(self):
        body = b"e" * 10000
        self.srv, url = serve(b"HTTP/1.1 500 Oops\r\nContent-Length: %d\r\n\r\n" % len(body) + body, b"")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(url, timeout=30)
        self.assertEqual(auth.error_text(caught.exception), "e" * 300)

    def test_the_socket_timeout_is_put_back(self):
        # Cut short, so the reply (and its socket) is still open afterwards.
        self.srv, url = serve(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nabcdefghij", b"")
        with urllib.request.urlopen(url, timeout=30) as r:
            sock = files._socket(r)
            self.assertIsNotNone(sock)
            self.assertEqual(files.read_reply(r, limit=3, cut=True), b"abc")
            self.assertEqual(sock.gettimeout(), 30)


class AccountDeadlineTest(unittest.TestCase):
    def test_a_stalled_account_is_offline_and_the_sync_goes_on(self):
        stall = lambda *_: time.sleep(10)
        account = {"name": "Slow", "provider": "caldav", "url": "https://dav.example.com/", "user": "me"}
        with mock.patch.object(sync, "ACCOUNT_DEADLINE", 1), \
                mock.patch.object(caldav, "login", return_value=None), \
                mock.patch.object(caldav, "calendars", side_effect=stall), \
                mock.patch.object(auth, "hidden_calendars", return_value={}):
            start = time.monotonic()
            st = sync.sync_account(account, False, lambda *_: None)
        self.assertLess(time.monotonic() - start, 2.5)
        self.assertEqual(st["status"], "offline")


if __name__ == "__main__":
    unittest.main()
