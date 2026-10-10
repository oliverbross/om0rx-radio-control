#include <QApplication>
#include <QEventLoop>
#include <QHash>
#include <QSplashScreen>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTimer>
#include <QVector>
#include <cassert>

#include "HvRigControl/hvrigcontrol.h"
#include "om0rxstationgate.h"
#include "om0rxtxwatchdogedge.h"

// main.cpp normally owns this symbol. This test links the real release object
// graph without main.o so it can instantiate the actual HvRigControl.
QSplashScreen *splash = nullptr;

int main(int argc, char **argv) {
    qputenv("QT_QPA_PLATFORM", "offscreen");
    QApplication app(argc, argv);

    // Native PTT may emit non-blocking station-audit telemetry, but it must
    // never make a synchronous station-ready/permit/final/veto request.
    QTcpServer server;
    assert(server.listen(QHostAddress::LocalHost, 0));
    qputenv("OM0RX_API_BASE", QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
    int apiRequests = 0;
    QVector<QByteArray> apiPayloads;
    QHash<QTcpSocket *, QByteArray> requestBuffers;
    QObject::connect(&server, &QTcpServer::newConnection, [&]() {
        while (server.hasPendingConnections()) {
            QTcpSocket *socket = server.nextPendingConnection();
            ++apiRequests;
            requestBuffers.insert(socket, QByteArray());
            QObject::connect(socket, &QTcpSocket::readyRead, [&, socket]() {
                QByteArray &payload = requestBuffers[socket];
                payload.append(socket->readAll());
                const int headerEnd = payload.indexOf("\r\n\r\n");
                if (headerEnd < 0) return;
                int contentLength = 0;
                const QList<QByteArray> headers = payload.left(headerEnd).split('\n');
                for (QByteArray header : headers) {
                    header = header.trimmed();
                    if (header.toLower().startsWith("content-length:"))
                        contentLength = header.mid(header.indexOf(':') + 1).trimmed().toInt();
                }
                if (payload.size() < headerEnd + 4 + contentLength) return;
                apiPayloads.append(payload.left(headerEnd + 4 + contentLength));
                requestBuffers.remove(socket);
                socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}");
                socket->disconnectFromHost();
            });
            QObject::connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
        }
    });

    HvRigControl rig;
    QVector<bool> outputEdges;
    rig.SetOm0rxPttOutputForTest([&](bool transmit, int id) {
        assert(id == 1);
        outputEdges.append(transmit);
    });

    // No prepared/confirmed/consumable station permit exists. An accepted
    // native AUTO slot must still reach the real native output dispatcher.
    Om0rxStationGate::invalidate("native-direct-ptt-test");
    Om0rxStationGate::currentHz() = 14074000;
    assert(!Om0rxStationGate::hasPermit());
    rig.InvokeOm0rxPttForTest(true, 1);
    assert(outputEdges.size() == 1 && outputEdges.last());
    assert(Om0rxStationGate::pttMask() == 1);

    // The paired false edge remains direct and releases the native output.
    rig.InvokeOm0rxPttForTest(false, 1);
    assert(outputEdges.size() == 2 && !outputEdges.last());
    assert(Om0rxStationGate::pttMask() == 0);
    assert(!Om0rxTxWatchdogEdge::shouldTrip(false, 1, 2));

    // A simulated continuously asserted PTT at the exact armed generation is
    // the only watchdog condition. Its emergency path must force native RX.
    rig.InvokeOm0rxPttForTest(true, 1);
    assert(Om0rxTxWatchdogEdge::shouldTrip(true, 7, 7));
    Om0rxStationGate::invalidate("tx-watchdog-stop");
    rig.InvokeOm0rxPttForTest(false, 1);
    assert(outputEdges.size() == 4 && !outputEdges.last());
    assert(Om0rxStationGate::pttMask() == 0);

    // Explicit Halt/emergency invalidation remains independent of ordinary
    // native PTT authorization. Its forced RX edge must always be delivered.
    rig.InvokeOm0rxPttForTest(true, 1);
    assert(outputEdges.last() && Om0rxStationGate::pttMask() == 1);
    Om0rxStationGate::invalidate("stop-tx-global");
    rig.InvokeOm0rxPttForTest(false, 1);
    assert(outputEdges.size() == 6 && !outputEdges.last());
    assert(Om0rxStationGate::pttMask() == 0);

    // Give queued network events a chance to surface. Native PTT may report
    // its edges asynchronously, but must not call a station authorization API.
    QEventLoop settle;
    QTimer::singleShot(100, &settle, &QEventLoop::quit);
    settle.exec();
    assert(apiRequests > 0);
    assert(apiPayloads.size() == apiRequests);
    for (const QByteArray &payload : apiPayloads) {
        const QByteArray requestLine = payload.left(payload.indexOf("\r\n"));
        assert(requestLine.startsWith("POST /api/digital/station-audit "));
        assert(payload.contains("\"event\":\"ptt-edge\""));
        assert(payload.contains("rising") || payload.contains("falling"));
        for (const QByteArray &forbidden : {
                 QByteArray("station-ready"), QByteArray("prepare"),
                 QByteArray("final"), QByteArray("permit"),
                 QByteArray("consume"), QByteArray("veto"),
                 QByteArray("ptt-rejected")}) {
            assert(!payload.contains(forbidden));
        }
    }
    return 0;
}
