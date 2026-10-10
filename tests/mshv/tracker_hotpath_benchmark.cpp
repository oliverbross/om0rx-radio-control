#include <QCoreApplication>
#include <QTemporaryDir>
#include <QDir>
#include <QFile>
#include <QElapsedTimer>
#include <QTextStream>
#include <cassert>
#include "hvdxcctracker.h"

static void write(const QString &path, const QByteArray &data) {
    QFile f(path); assert(f.open(QIODevice::WriteOnly)); assert(f.write(data) == data.size());
}
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    QTemporaryDir dir;
    QDir().mkpath(dir.path() + "/settings/database");
    QByteArray cty, mapping, adif;
    const QStringList bands = QStringList() << "160m" << "80m" << "40m" << "30m" << "20m" << "17m" << "15m" << "12m" << "10m";
    for (int i = 1; i <= 300; ++i) {
        const QString prefix = QString("X%1Z").arg(i);
        cty += QString("Entity %1: %2: %3: EU: 0: 0: 0: %4: %4;\n")
            .arg(i).arg(i % 40 + 1).arg(i % 90 + 1).arg(prefix).toUtf8();
        mapping += QString("%1:%2\n").arg(prefix).arg(i).toUtf8();
        for (const QString &band : bands) {
            const QString call = prefix + "AA";
            adif += QString("<CALL:%1>%2<BAND:%3>%4<MODE:3>FT8<QSO_DATE:8>20261007<EOR>\n")
                .arg(call.size()).arg(call).arg(band.size()).arg(band).toUtf8();
        }
    }
    write(dir.path() + "/settings/database/cty.dat", cty);
    write(dir.path() + "/settings/database/dxcc_numbers.dat", mapping);
    write(dir.path() + "/history.adi", adif);
    HvDxccTracker tracker(dir.path());
    assert(tracker.initDatabase());
    tracker.importFromAdifLog(dir.path() + "/history.adi");
    assert(tracker.getWorkedDxccCountAllTime() == 300);
    QElapsedTimer clock; clock.start();
    int matches = 0;
    for (int i = 0; i < 8000; ++i) {
        matches += tracker.isContinentWorked("AF", 8);
        matches += tracker.isCqZoneWorked(40, 8);
        matches += tracker.isItuZoneWorked(90, 8);
        matches += tracker.isContinentWorkedAllTime("AF");
        matches += tracker.isCqZoneWorkedAllTime(40);
        matches += tracker.isItuZoneWorkedAllTime(90);
    }
    assert(matches == 32000);
    QTextStream(stdout) << "production tracker: 300 entities, 2700 band slots, 48000 queries, elapsed_us="
                        << clock.nsecsElapsed()/1000 << Qt::endl;
}
