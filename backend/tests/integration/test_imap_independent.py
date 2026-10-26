"""Cross-check against an independent IMAP implementation (pymap), so the client is not only validated against our own fake."""
import imaplib
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.adapters.channels.imap import ImapClient, ImapError
from app.db import session_factory
from app.models import ChannelAccount, Message
from app.services import mailsync
from tests.fakes import mail
from tests.fakes.smtp_sink import Sink
from tests.helpers import H, Site, biz_time, make_world, run_sends
from tests.integration.test_mail_sync import add_account

pymap_bin = Path(sys.executable).parent / "pymap"
pytestmark = pytest.mark.skipif(not pymap_bin.exists(), reason="pymap not installed (pip install pymap)")


@pytest.fixture
def server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([str(pymap_bin), "--host", "127.0.0.1", "--port", str(port), "--no-tls", "dict"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.skip("pymap did not start")
    yield SimpleNamespace(port=port, user="demouser", password="demopass")
    proc.kill()


def append(srv, raw: bytes):
    c = imaplib.IMAP4("127.0.0.1", srv.port)
    c.login(srv.user, srv.password)
    assert c.append("INBOX", None, None, raw)[0] == "OK"
    c.logout()


def test_client_against_independent_server(server):
    cl = ImapClient("127.0.0.1", server.port, server.user, server.password, "none")
    assert cl.check() == 0
    append(server, mail.reply("a@b.com", "me@x.com", "hello one"))
    append(server, mail.dsn("<o@x>", "g@a.com"))
    first = cl.fetch_new(None, None, 7, 50)
    assert [len(b) > 100 for _, b in first.messages] == [True, True]
    assert first.highest_uid == first.messages[-1][0] and not first.more
    append(server, mail.reply("c@d.com", "me@x.com", "two"))
    nxt = cl.fetch_new(first.messages[-1][0], first.uidvalidity, 7, 50)
    assert len(nxt.messages) == 1 and nxt.messages[0][0] == first.messages[-1][0] + 1
    assert cl.fetch_new(nxt.messages[-1][0], first.uidvalidity, 7, 50).messages == []        # `n:*` quirk handled
    batch = cl.fetch_new(None, None, 7, 1)
    assert len(batch.messages) == 1 and batch.more is True
    with pytest.raises(ImapError):
        ImapClient("127.0.0.1", server.port, server.user, "wrong", "none").check()


def test_send_over_smtp_and_receive_reply_over_independent_imap(client, server, db):
    site, smtp = Site(), Sink().start()
    try:
        acct = add_account(client, smtp, server)
        c, *_ = make_world(client, site.url, mock=False, campaign={"channel_account_id": acct["id"]})
        client.post(f"/api/v1/campaigns/{c['id']}/launch", headers=H)
        run_sends(biz_time())
        mid = db.scalars(select(Message).where(Message.direction == "out")).one().message_id_header
        append(server, mail.reply("Asha <asha@brightsmile.in>", "sales@flowhq-mail.com", "Yes, please send pricing.", in_reply_to=mid))
        with session_factory()() as s:
            stats = mailsync.sync_account(s, s.get(ChannelAccount, uuid.UUID(acct["id"])))
        assert stats["reply"] == 1
        db.expire_all()
        m = db.scalars(select(Message).where(Message.direction == "in")).one()
        assert m.intent == "requesting_info" and m.body == "Yes, please send pricing."
    finally:
        site.close()
        smtp.stop()
