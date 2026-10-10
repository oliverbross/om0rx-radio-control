#include <cassert>
#include <QDateTime>
#include <QFile>
#include <QTemporaryDir>

#include "awardhuntingpolicy.h"

int main()
{
    QTemporaryDir dir;
    assert(dir.isValid());
    QFile file(dir.path() + "/award_hunting.json");
    assert(file.open(QIODevice::WriteOnly));
    const QString now = QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
    const QString expiry = QDateTime::currentDateTimeUtc().addSecs(600).toString(Qt::ISODate);
    const QByteArray payload = QString(
        "{\"schema\":1,\"history_authoritative\":true,\"activations\":[{"
        "\"callsign\":\"REF1\",\"program\":\"POTA\",\"reference\":\"K-0001\","
        "\"band\":\"30m\",\"mode\":\"FT8\",\"spotted_at_utc\":\"%1\","
        "\"expires_at_utc\":\"%2\",\"slot_key\":\"POTA:K-0001@30m@FT8\","
        "\"history_status\":\"authoritative\",\"gaps\":{\"new_reference\":true}},{"
        "\"callsign\":\"REF1\",\"program\":\"SOTA\",\"reference\":\"W1/AA-001\","
        "\"band\":\"30m\",\"mode\":\"FT8\",\"spotted_at_utc\":\"%1\","
        "\"expires_at_utc\":\"%2\",\"slot_key\":\"SOTA:W1/AA-001@30m@FT8\","
        "\"history_status\":\"authoritative\",\"gaps\":{\"new_reference\":true}}]}")
        .arg(now, expiry).toUtf8();
    assert(file.write(payload) == payload.size());
    file.close();

    AwardActivationIndex index;
    assert(index.load(file.fileName()));
    AwardHuntingConfig config;
    const AwardReferenceScore score = index.score(
        "REF1", "30m", "FT8", true, QDateTime::currentDateTimeUtc(), config);
    assert(score.eligible && score.matches.size() == 2);

    // The structured selection survives the same three persistent columns
    // used by HvLogW before being rendered into distinct standard ADIF fields.
    const QString pota = AwardAdifPolicy::encodeProgramReferences(score.matches, "POTA");
    const QString sota = AwardAdifPolicy::encodeProgramReferences(score.matches, "SOTA");
    const QString wwff = AwardAdifPolicy::encodeProgramReferences(score.matches, "WWFF");
    assert(pota == "K-0001" && sota == "W1/AA-001" && wwff.isEmpty());
    const QString adif = AwardAdifPolicy::adifFields(
        AwardAdifPolicy::fromProgramColumns(pota, sota, wwff));
    assert(adif.contains("<POTA_REF:6>K-0001"));
    assert(adif.contains("<SOTA_REF:9>W1/AA-001"));
    assert(!adif.contains("<SIG:"));

    AwardReferenceMatch single;
    single.program = "WWFF";
    single.reference = "DLFF-0001";
    const QString singleAdif = AwardAdifPolicy::adifFields(
        QList<AwardReferenceMatch>() << single);
    assert(singleAdif.contains("<WWFF_REF:9>DLFF-0001"));
    assert(singleAdif.contains("<SIG:4>WWFF"));
    assert(singleAdif.contains("<SIG_INFO:9>DLFF-0001"));

    // Regression: multiplication is qint64 and saturates before narrowing.
    BandProductivityTracker tracker;
    PropagationAdaptationConfig propagation;
    propagation.windowSeconds = 86400;
    propagation.uniqueDecodeWeight = 100000;
    propagation.distantDecodeWeight = 100000;
    propagation.maxBandBoost = 100000;
    const QDateTime observed = QDateTime::currentDateTimeUtc();
    for (int i = 0; i < 25000; ++i)
        tracker.observeDecode(7, "K" + QString::number(i) + "A", true, observed);
    assert(tracker.score(7, observed, propagation) == 100000);

    return 0;
}
