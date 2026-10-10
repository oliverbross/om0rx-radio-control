#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>
#include <cassert>

#include "HvAutoDxer/autodxstatusownership.h"
#include "HvAutoDxer/autodxstatusprovenance.h"

static void apply(const AutoDxStatusOwnership::Decision &decision,
                  QString &legacyCall, QString &statusCall, QString &statusGrid)
{
    if (decision.action == AutoDxStatusOwnership::SetOwnedTarget) {
        legacyCall = decision.callsign;
        statusCall = decision.callsign;
        statusGrid = decision.grid;
    } else if (decision.action == AutoDxStatusOwnership::ClearOwnedTarget) {
        legacyCall.clear();
        statusCall.clear();
        statusGrid.clear();
    }
}

static void writeRaw(const QString &path, const QByteArray &contents)
{
    QFile file(path);
    assert(file.open(QIODevice::WriteOnly));
    assert(file.write(contents) == contents.size());
}

int main()
{
    QString legacyCall;
    QString statusCall;
    QString statusGrid;
    AutoDxStatusOwnership ownership;

    apply(ownership.targetChanged("9t0md", "jn94", false,
                                  legacyCall, statusCall),
          legacyCall, statusCall, statusGrid);
    assert(legacyCall == "9T0MD" && statusCall == "9T0MD");
    assert(statusGrid == "JN94");
    apply(ownership.targetChanged("", "", false, legacyCall, statusCall),
          legacyCall, statusCall, statusGrid);
    assert(legacyCall.isEmpty() && statusCall.isEmpty() && statusGrid.isEmpty());

    apply(ownership.targetChanged("HA3JB", "JN97", false,
                                  legacyCall, statusCall),
          legacyCall, statusCall, statusGrid);
    apply(ownership.targetChanged("", "", true, legacyCall, statusCall),
          legacyCall, statusCall, statusGrid);
    assert(legacyCall == "HA3JB" && statusCall == "HA3JB");
    apply(ownership.targetChanged("", "", false, legacyCall, statusCall),
          legacyCall, statusCall, statusGrid);
    assert(legacyCall.isEmpty() && statusCall.isEmpty());

    // Equal fresh-start caches are not ownership evidence.
    AutoDxStatusOwnership freshManual;
    legacyCall = "TA3XEE";
    statusCall = "TA3XEE";
    QString legacyGrid = "KM69";
    statusGrid = "KM69";
    const AutoDxStatusOwnership::Decision manualDecision =
        freshManual.targetChanged("", "", false, legacyCall, statusCall,
                                  legacyGrid, statusGrid, "", "", true);
    assert(manualDecision.action == AutoDxStatusOwnership::NoChange);
    assert(legacyCall == "TA3XEE" && statusCall == "TA3XEE");

    // A valid durable marker waits through partial cache hydration, then
    // clears the exact AutoDX-owned persisted pair.
    AutoDxStatusOwnership restart;
    legacyCall.clear();
    statusCall.clear();
    legacyGrid.clear();
    statusGrid.clear();
    assert(restart.targetChanged("", "", false, legacyCall, statusCall,
                                 legacyGrid, statusGrid, "OM5CM", "JN98DF", true).action
           == AutoDxStatusOwnership::NoChange);
    legacyCall = "OM5CM";
    legacyGrid = "JN98DF";
    assert(restart.targetChanged("", "", false, legacyCall, statusCall,
                                 legacyGrid, statusGrid, "OM5CM", "JN98DF", true).action
           == AutoDxStatusOwnership::NoChange);
    statusCall = "OM5CM";
    statusGrid = "JN98DF";
    apply(restart.targetChanged("", "", false, legacyCall, statusCall,
                                legacyGrid, statusGrid, "OM5CM", "JN98DF", true),
          legacyCall, statusCall, statusGrid);
    assert(legacyCall.isEmpty() && statusCall.isEmpty() && statusGrid.isEmpty());

    // Engagement and foreign replacement are protected even with provenance.
    legacyCall = "OM5CM";
    statusCall = "OM5CM";
    legacyGrid = "JN98DF";
    statusGrid = "JN98DF";
    assert(restart.targetChanged("", "", true, legacyCall, statusCall,
                                 legacyGrid, statusGrid, "OM5CM", "JN98DF", true).action
           == AutoDxStatusOwnership::NoChange);
    legacyCall = "TA3XEE";
    statusCall = "TA3XEE";
    legacyGrid = "KM69";
    statusGrid = "KM69";
    const AutoDxStatusOwnership::Decision foreign =
        restart.targetChanged("", "", false, legacyCall, statusCall,
                              legacyGrid, statusGrid, "OM5CM", "JN98DF", true);
    assert(foreign.action == AutoDxStatusOwnership::RetireProvenance);
    assert(legacyCall == "TA3XEE" && statusCall == "TA3XEE");

    legacyCall.clear();
    statusCall.clear();
    statusGrid.clear();
    apply(ownership.targetChanged("BG0EMF", "NN33", false,
                                  legacyCall, statusCall),
          legacyCall, statusCall, statusGrid);
    legacyCall = "TA3XEE";
    statusCall = "TA3XEE";
    const AutoDxStatusOwnership::Decision replacement =
        ownership.targetChanged("", "", false, legacyCall, statusCall);
    assert(replacement.action == AutoDxStatusOwnership::RetireProvenance);
    assert(legacyCall == "TA3XEE" && statusCall == "TA3XEE");

    // Atomic marker replacement and strict malformed/stale fail-closed rules.
    QTemporaryDir directory;
    assert(directory.isValid());
    const QString markerPath = directory.path() + "/database/autodx_status_owner.json";
    const QDateTime now = QDateTime::fromString("2026-10-06T12:00:00Z", Qt::ISODate);
    assert(AutoDxStatusProvenance::store(markerPath, "OM5CM", "JN98DF", now));
    AutoDxStatusProvenance::Marker marker;
    assert(AutoDxStatusProvenance::load(markerPath, marker, now.addSecs(10)));
    assert(marker.callsign == "OM5CM" && marker.grid == "JN98DF");
    assert(AutoDxStatusProvenance::store(markerPath, "9T0MD", "JN94", now.addSecs(20)));
    assert(AutoDxStatusProvenance::load(markerPath, marker, now.addSecs(30)));
    assert(marker.callsign == "9T0MD" && marker.grid == "JN94");

    writeRaw(markerPath, "{not-json");
    assert(!AutoDxStatusProvenance::load(markerPath, marker, now));
    QJsonObject stale;
    stale["schema"] = 1;
    stale["owner"] = "mshv-native-autodx";
    stale["callsign"] = "OM5CM";
    stale["grid"] = "JN98DF";
    stale["written_at_utc"] = now.addSecs(
        -AutoDxStatusProvenance::maximumAgeSeconds() - 1).toString(Qt::ISODateWithMs);
    writeRaw(markerPath, QJsonDocument(stale).toJson(QJsonDocument::Compact));
    assert(!AutoDxStatusProvenance::load(markerPath, marker, now));
    assert(AutoDxStatusProvenance::clear(markerPath));
    assert(!QFile::exists(markerPath));

    return 0;
}
