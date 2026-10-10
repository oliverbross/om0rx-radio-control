#include <QCoreApplication>
#include <QTcpServer>
#include <QTcpSocket>
#include <QEventLoop>
#include <QElapsedTimer>
#include <cassert>
#define OM0RX_STATION_GATE_TESTING 1
#include "om0rxstationgate.h"

// Local fake HTTP server only. Never talks to the application or radio.
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    QTcpServer server;
    assert(server.listen(QHostAddress::LocalHost, 0));
    qputenv("OM0RX_API_BASE", QString("http://127.0.0.1:%1").arg(server.serverPort()).toUtf8());
    int responseMode = 0;
    int consumeMode = 0;
    int consumeRequests = 0;
    int permitSerial = 0;
    QObject::connect(&server, &QTcpServer::newConnection, [&]() {
        QTcpSocket *socket = server.nextPendingConnection();
        QObject::connect(socket, &QTcpSocket::readyRead, socket,
                         [socket, &responseMode, &consumeMode, &consumeRequests, &permitSerial]() {
            QByteArray data = socket->property("request_bytes").toByteArray() + socket->readAll();
            socket->setProperty("request_bytes", data);
            const int split = data.indexOf("\r\n\r\n");
            if (split < 0) return;
            const QJsonObject request = QJsonDocument::fromJson(data.mid(split+4)).object();
            if (request.isEmpty()) return;
            assert(request.value("provider").toString() == "mshv_auto_dx");
            assert(request.value("authorization_generation").isDouble());
            if (request.contains("permit_nonce")) {
                ++consumeRequests;
                assert(request.value("frequency_hz").toInt() == 14074000);
                assert(request.value("mode").toString() == "DIGU");
                assert(request.value("path").toString() == "native-test");
                if (consumeMode == 2) return;
                QJsonObject consumed;
                consumed["success"] = consumeMode == 0;
                consumed["reason"] = consumeMode == 0 ? "permit-consumed" : "permit-revoked";
                const QByteArray body = QJsonDocument(consumed).toJson(QJsonDocument::Compact);
                const auto sendConsume = [socket, body]() {
                    if (socket->state() == QAbstractSocket::UnconnectedState) return;
                    socket->write("HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body);
                    socket->disconnectFromHost();
                };
                if (consumeMode == 3) QTimer::singleShot(Om0rxStationGate::consumeTimeoutMs() + 200, socket, sendConsume);
                else sendConsume();
                return;
            }
            assert(request.value("band").toString() == "20m");
            const QString phase = request.value("phase").toString();
            assert(phase == "prepare" || phase == "final");
            if (phase == "final") assert(request.value("prepare_nonce").toString() == "prepare-one");
            if (responseMode == 3) return;
            QJsonObject result;
            result["ready"] = responseMode != 1;
            result["request_id"] = responseMode == 2 ? "wrong-id" : request.value("request_id");
            result["phase"] = phase;
            result["prepared"] = true;
            result["transmit_ready"] = phase == "final";
            if (phase == "prepare") {
                result["prepare_nonce"] = "prepare-one";
                result["prepare_expires_in_ms"] = 90000;
            } else {
                result["permit_nonce"] = QString("permit-%1").arg(++permitSerial);
                result["permit_expires_in_ms"] = 45000;
            }
            const QByteArray body = QJsonDocument(result).toJson(QJsonDocument::Compact);
            const QByteArray status = responseMode == 5 ? "500 Internal Server Error" : "200 OK";
            const auto sendResponse = [socket, status, body]() {
                if (socket->state() == QAbstractSocket::UnconnectedState) return;
                socket->write("HTTP/1.1 " + status + "\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: " + QByteArray::number(body.size()) + "\r\n\r\n" + body);
                socket->disconnectFromHost();
            };
            if (responseMode == 6) QTimer::singleShot(7200, socket, sendResponse);
            else sendResponse();
        });
        QObject::connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
    });

    assert(Om0rxStationGate::requestTimeoutMs() == 75000);
    assert(Om0rxStationGate::consumeTimeoutMs() == 1500);

    // The ordinary empty-queue EmitStopAuto path calls this exact gate method.
    // While a fake prepare is in flight it must not change generation, cancel
    // the request, or prevent the returned preparation nonce from committing.
    responseMode = 0;
    Om0rxStationGate::invalidate("empty-queue-stop-test-reset");
    Om0rxStationGate::currentHz() = 14074000;
    Om0rxStationGate::autoDesired() = true;
    const unsigned emptyQueueGeneration = Om0rxStationGate::generation();
    QEventLoop emptyQueueLoop;
    bool emptyQueuePrepared = false;
    (new Om0rxStationGate(&app))->prepare(14074000, "20m", [&](bool value) {
        emptyQueuePrepared = value;
        emptyQueueLoop.quit();
    });
    assert(Om0rxStationGate::pending());
    Om0rxStationGate::noteInternalAutoStopped();
    assert(!Om0rxStationGate::autoDesired());
    assert(Om0rxStationGate::generation() == emptyQueueGeneration);
    QTimer::singleShot(5000, &emptyQueueLoop, &QEventLoop::quit);
    emptyQueueLoop.exec();
    assert(emptyQueuePrepared);
    assert(Om0rxStationGate::generation() == emptyQueueGeneration);
    assert(Om0rxStationGate::prepareNonce() == "prepare-one");

    // Process teardown is an explicit lifecycle edge. It must advance the
    // generation, retire an in-flight request, and deny the returned nonce.
    responseMode = 0;
    Om0rxStationGate::invalidate("teardown-test-reset");
    Om0rxStationGate::currentHz() = 14074000;
    const unsigned teardownGeneration = Om0rxStationGate::generation();
    QEventLoop teardownLoop;
    bool teardownPrepared = true;
    (new Om0rxStationGate(&app))->prepare(14074000, "20m", [&](bool value) {
        teardownPrepared = value;
        teardownLoop.quit();
    });
    assert(Om0rxStationGate::pending());
    Om0rxStationGate::invalidate("process-teardown");
    assert(Om0rxStationGate::generation() == teardownGeneration + 1);
    QTimer::singleShot(5000, &teardownLoop, &QEventLoop::quit);
    teardownLoop.exec();
    assert(!teardownPrepared);
    assert(Om0rxStationGate::prepareNonce().isEmpty());

    Om0rxStationGate::invalidate("sequence-test-reset");
    Om0rxStationGate::currentHz() = 14074000;
    const unsigned sequenceGeneration = Om0rxStationGate::generation();
    const quint64 txSequence = Om0rxStationGate::notePttRequest(true, 1);
    assert(Om0rxStationGate::pttRequestStillCurrent(
        txSequence, sequenceGeneration, 14074000, 1));
    Om0rxStationGate::notePttRequest(false, 1);
    assert(!Om0rxStationGate::pttRequestStillCurrent(
        txSequence, sequenceGeneration, 14074000, 1));
    const quint64 laterTxSequence = Om0rxStationGate::notePttRequest(true, 1);
    Om0rxStationGate::currentHz() = 7074000;
    assert(!Om0rxStationGate::pttRequestStillCurrent(
        laterTxSequence, sequenceGeneration, 14074000, 1));
    Om0rxStationGate::invalidate("sequence-test-finished");
    assert(Om0rxStationGate::requestedPttMask() == 0);
    assert(Om0rxStationGate::pttMask() == 0);
    for (int mode=0; mode<6; ++mode) {
        responseMode = mode;
        Om0rxStationGate::invalidate("test-reset");
        Om0rxStationGate::currentHz() = 14074000;
        QEventLoop loop;
        bool ready = true;
        Om0rxStationGate *gate = mode == 3
            ? new Om0rxStationGate(&app, 100)
            : new Om0rxStationGate(&app);
        gate->prepare(14074000, mode == 0 ? QString() : QString("20m"), [&](bool value) { ready=value; loop.quit(); });
        assert(Om0rxStationGate::pending());
        assert(!Om0rxStationGate::hasPermit());
        if (mode == 4) Om0rxStationGate::invalidate("halt-before-response");
        QTimer::singleShot(mode == 3 ? 1000 : 5000, &loop, &QEventLoop::quit);
        loop.exec();
        assert(ready == (mode == 0));
        assert(!Om0rxStationGate::pending());
        assert(!Om0rxStationGate::hasPermit());
        if (mode == 0) {
            QEventLoop finalLoop;
            (new Om0rxStationGate(&app))->confirm(14074000, "20m", [&](bool value) { ready=value; finalLoop.quit(); });
            QTimer::singleShot(5000, &finalLoop, &QEventLoop::quit);
            finalLoop.exec();
            assert(ready && Om0rxStationGate::hasPermit());
            Om0rxStationGate consumeGate(&app);
            QElapsedTimer consumeElapsed;
            consumeElapsed.start();
            assert(consumeGate.consumePermitBlocking("native-test"));
            assert(consumeElapsed.elapsed() < Om0rxStationGate::consumeTimeoutMs());
            assert(!Om0rxStationGate::hasPermit());
            assert(!consumeGate.consumePermitBlocking("native-test"));
        }
        Om0rxStationGate::currentHz() = 7074000;
        assert(!Om0rxStationGate::hasPermit());
    }

    // A legal accessory response longer than the old 4/15 second assumptions
    // succeeds inside the single documented 75 second client budget.
    responseMode = 6;
    Om0rxStationGate::invalidate("delayed-response-test");
    Om0rxStationGate::currentHz() = 14074000;
    QElapsedTimer delayed;
    delayed.start();
    QEventLoop delayedLoop;
    bool delayedReady = false;
    (new Om0rxStationGate(&app))->prepare(14074000, "20m", [&](bool value) {
        delayedReady = value;
        delayedLoop.quit();
    });
    QTimer::singleShot(Om0rxStationGate::requestTimeoutMs() + 1000, &delayedLoop, &QEventLoop::quit);
    delayedLoop.exec();
    assert(delayedReady);
    assert(delayed.elapsed() >= 7000);
    assert(delayed.elapsed() < Om0rxStationGate::requestTimeoutMs());
    assert(!Om0rxStationGate::hasPermit());

    // Exercise the real RX prepare -> final -> authoritative consume loop for
    // three consecutive FT8 periods. No local nonce injection is permitted.
    responseMode = 0;
    consumeMode = 0;
    Om0rxStationGate::currentHz() = 14074000;
    for (int cycle=0; cycle<3; ++cycle) {
        QEventLoop prepareLoop;
        bool cyclePrepared = false;
        (new Om0rxStationGate(&app))->prepare(14074000, "20m", [&](bool value) {
            cyclePrepared = value; prepareLoop.quit();
        });
        QTimer::singleShot(5000, &prepareLoop, &QEventLoop::quit);
        prepareLoop.exec();
        assert(cyclePrepared);
        QEventLoop finalLoop;
        bool cycleFinal = false;
        (new Om0rxStationGate(&app))->confirm(14074000, "20m", [&](bool value) {
            cycleFinal = value; finalLoop.quit();
        });
        QTimer::singleShot(5000, &finalLoop, &QEventLoop::quit);
        finalLoop.exec();
        assert(cycleFinal && Om0rxStationGate::hasPermit());
        Om0rxStationGate consumeGate(&app);
        assert(consumeGate.consumePermitBlocking("native-test"));
        assert(!Om0rxStationGate::hasPermit());
    }
    assert(consumeRequests == 4);

    // A halt/QSY between final approval and the hardware edge clears both the
    // nonce and requested-output mask, so no consume request can be sent.
    Om0rxStationGate::permitHz() = 14074000;
    Om0rxStationGate::permitNonce() = "halted-permit";
    Om0rxStationGate::permitExpiresAt() = QDateTime::currentMSecsSinceEpoch() + 30000;
    Om0rxStationGate::pttMask() = 3;
    const int beforeHaltConsume = consumeRequests;
    Om0rxStationGate::invalidate("halt-before-edge");
    assert(Om0rxStationGate::pttMask() == 0);
    Om0rxStationGate haltGate(&app);
    assert(!haltGate.consumePermitBlocking("native-test"));
    assert(consumeRequests == beforeHaltConsume);

    // A server rejection or a lost response never authorizes hardware and the
    // ambiguous local nonce is retired rather than replayed.
    for (int mode : {1, 3}) {
        consumeMode = mode;
        Om0rxStationGate::currentHz() = 14074000;
        Om0rxStationGate::permitHz() = 14074000;
        Om0rxStationGate::permitNonce() = QString("reject-%1").arg(mode);
        Om0rxStationGate::permitExpiresAt() = QDateTime::currentMSecsSinceEpoch() + 30000;
        Om0rxStationGate rejectGate(&app);
        assert(!rejectGate.consumePermitBlocking("native-test"));
        assert(!Om0rxStationGate::hasPermit());
    }
    consumeMode = 0;

    qputenv("OM0RX_API_BASE", "http://example.com");
    bool refused = false;
    (new Om0rxStationGate(&app))->confirm(14074000, "20m", [&](bool ready) { refused = !ready; });
    assert(refused && !Om0rxStationGate::pending());
    return 0;
}
