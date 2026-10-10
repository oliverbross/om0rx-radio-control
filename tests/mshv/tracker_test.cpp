#include <QCoreApplication>
#include <QTemporaryDir>
#include <QDir>
#include <QFile>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QVariant>
#include <cassert>
#include "HvDxccTracker/hvdxcctracker.h"
#include "HvAutoDxer/dxcctracker.h"

static void writeFixture(const QString &path, const QByteArray &data) {
    QFile file(path); assert(file.open(QIODevice::WriteOnly));
    assert(file.write(data) == data.size());
}
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    QTemporaryDir dir;
    assert(dir.isValid());
    QDir().mkpath(dir.path()+"/settings/database");
    // Swap official IDs to reproduce destructive in-place remapping collisions.
    writeFixture(dir.path()+"/settings/database/cty.dat",
        "Country A: 1: 1: EU: 0: 0: 0: A: A,AA,=A1EX;\nCountry B: 2: 2: EU: 0: 0: 0: B: B,BB,=B1EX;\n");
    writeFixture(dir.path()+"/settings/database/dxcc_numbers.dat", "A:2\nB:1\n");
    writeFixture(dir.path()+"/settings/database/confirmed-dxcc.txt", "Country A\n");
    HvDxccTracker tracker(dir.path());
    assert(tracker.initDatabase());
    assert(tracker.getTotalDxccEntities() == 2);
    assert(tracker.getDxccNumber("AA1ZZ") == 2);
    assert(tracker.getDxccNumber("A1EX") == 2);
    assert(tracker.getDxccNumber("BB1ZZ") == 1);
    assert(tracker.getDxccNumber("B1EX") == 1);
    writeFixture(dir.path()+"/history.adi",
        "<CALL:5>A1AAA<BAND:3>20m<MODE:3>FT8<QSO_DATE:8>20261001<EOR>\n"
        "<CALL:5>B1BBB<BAND:3>40m<MODE:3>FT4<QSO_DATE:8>20261001<EOR>\n"
        "<CALL:5>A1CCC<BAND:3>15m<MODE:4>MFSK<SUBMODE:3>FT4<QSO_DATE:8>20261001<EOR>\n"
        "<CALL:5>B1DDD<BAND:3>10m<MODE:2>CW<QSO_DATE:8>20261001<EOR>\n");
    tracker.importFromAdifLog(dir.path()+"/history.adi");
    assert(tracker.isCallWorked("A1AAA",8,"FT8"));
    assert(!tracker.isCallWorked("A1AAA",8,"FT4"));
    assert(tracker.isCallWorkedOnBand("A1AAA",8));
    assert(!tracker.isCallWorkedOnBand("A1AAA",6));
    assert(tracker.isCallWorked("B1BBB",6,"FT4"));
    assert(!tracker.isCallWorked("B1BBB",6,"FT8"));
    DxccTracker autoDxTracker(nullptr, &tracker);
    tracker.setCurrentMode("FT4");
    assert(!autoDxTracker.eligibilityFacts("B1BBB", QString(), 6).bandCall);
    tracker.setCurrentMode("FT8");
    assert(autoDxTracker.eligibilityFacts("B1BBB", QString(), 6).bandCall);
    assert(tracker.isCallWorked("A1CCC",10,"FT4"));
    assert(!tracker.isCallWorked("B1DDD",12,"CW"));
    assert(tracker.isDxccWorkedMode(1,6,"FT4"));
    assert(tracker.isDxccWorkedMode(2,10,"FT4"));
    assert(tracker.confirmationDataAvailable());
    assert(tracker.isDxccConfirmed(2));
    assert(!tracker.isDxccConfirmed(1));
    assert(tracker.applyWavelogAcknowledgedQso("delta-1", "A2NEW", "JN88AA", 8, "FT8", "20261004"));
    assert(tracker.applyWavelogAcknowledgedQso("delta-1", "A2NEW", "JN88AA", 8, "FT8", "20261004"));
    QSqlDatabase audit = QSqlDatabase::addDatabase("QSQLITE", "audit");
    audit.setDatabaseName(dir.path()+"/settings/database/worked.db");
    assert(audit.open());
    QSqlQuery ledger(audit);
    assert(ledger.exec("SELECT COUNT(*) FROM wavelog_applied_deltas"));
    assert(ledger.next() && ledger.value(0).toInt() == 1);
    assert(ledger.exec("SELECT qso_count FROM worked_dxcc WHERE entity_number=2 AND band_index=8 AND mode='FT8'"));
    assert(ledger.next() && ledger.value(0).toInt() == 2);
    // A statement failure after the ledger insert must roll back the entire
    // transition and must not contaminate the tracker's in-memory sets.
    assert(ledger.exec("CREATE TRIGGER fail_wavelog_delta_call BEFORE INSERT ON worked_calls "
                       "WHEN NEW.callsign='B2FAIL' BEGIN SELECT RAISE(ABORT, 'injected'); END"));
    assert(!tracker.applyWavelogAcknowledgedQso("delta-fail", "B2FAIL", "KN08AA", 10, "FT8", "20261004"));
    assert(!tracker.isCallWorked("B2FAIL",10,"FT8"));
    assert(ledger.exec("SELECT COUNT(*) FROM wavelog_applied_deltas WHERE delta_key='delta-fail'"));
    assert(ledger.next() && ledger.value(0).toInt() == 0);
    assert(ledger.exec("SELECT COUNT(*) FROM worked_dxcc WHERE entity_number=1 AND band_index=10 AND mode='FT8'"));
    assert(ledger.next() && ledger.value(0).toInt() == 0);
    assert(ledger.exec("DROP TRIGGER fail_wavelog_delta_call"));
    assert(tracker.applyWavelogAcknowledgedQso("delta-fail", "B2FAIL", "KN08AA", 10, "FT8", "20261004"));
    assert(tracker.isCallWorked("B2FAIL",10,"FT8"));
    assert(tracker.isContinentWorked("EU", 10));
    assert(tracker.isCqZoneWorked(2, 10));
    assert(tracker.isItuZoneWorked(2, 10));
    assert(!tracker.isCqZoneWorked(2, 12));
    assert(tracker.isCqZoneWorkedAllTime(2));
    assert(tracker.isItuZoneWorkedAllTime(1));
    assert(!tracker.isCqZoneWorked(0, 10));
    // Warm index must observe a subsequent acknowledged history update.
    assert(!tracker.isCqZoneWorked(2, 7));
    assert(tracker.applyWavelogAcknowledgedQso("index-update", "B3NEW", "KN08AA", 7, "FT8", "20261007"));
    assert(tracker.isCqZoneWorked(2, 7));
    assert(tracker.isItuZoneWorked(2, 7));
    tracker.clearAllWorkedData();
    assert(!tracker.isContinentWorkedAllTime("EU"));
    assert(!tracker.isCqZoneWorked(2, 7));
    assert(!tracker.isItuZoneWorkedAllTime(2));
    audit.close();
    return 0;
}
