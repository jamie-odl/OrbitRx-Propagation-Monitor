import socket
import threading

from orbitrx.dx import DxClusterService, parse_dx_line


def test_parse_dx_standard():
    line = "DX de W1AW: 14095 N4BP 2014Z"
    r = parse_dx_line(line)
    assert r is not None
    spotter, freq, target = r
    assert spotter == "W1AW"
    assert freq == 14.095
    assert target == "N4BP"


def test_cluster_stop_unblocks_a_recv():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client = socket.socket()
    client.connect(listener.getsockname())
    server, _ = listener.accept()
    server.settimeout(None)

    class _State:
        cluster_active = True

    service = DxClusterService(_State(), {}, lambda: None, lambda _status: None)
    service._socket = server
    done = threading.Event()

    def blocked():
        try:
            server.recv(16)
        except OSError:
            pass
        done.set()

    thread = threading.Thread(target=blocked)
    thread.start()
    assert not done.wait(0.2)
    service.stop()
    thread.join(2)
    client.close()
    listener.close()
    assert done.is_set()
    assert not thread.is_alive()


def test_parse_dx_spaced():
    line = "DX de VE3XYZ 14200 AB1CD 1234Z"
    r = parse_dx_line(line)
    assert r is not None
    assert r[1] == 14.2
