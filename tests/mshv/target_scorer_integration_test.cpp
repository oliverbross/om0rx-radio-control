#include <cassert>
#include <QElapsedTimer>
#include <QDebug>
#include <QTextStream>
#include <QTemporaryDir>
#include <QFile>

#include "autodxmessageparser.h"
#include "targetscorer.h"
#include "fake_target_scorer_dependencies.h"

static CachedDecode decode(const QString &call, const QString &grid, const QString &message)
{
    CachedDecode value;
    value.callsign = call;
    value.grid = grid;
    value.dxccEntity = QStringLiteral("Fixture Entity");
    value.originalMessage = message;
    value.bandIndex = 7;
    value.audioFrequency = 1000;
    value.dialFrequencyHz = 7074000;
    value.snr = -15;
    value.decodeCount = 1;
    value.isCQ = false;
    return value;
}

int main()
{
    // Sender extraction is protocol-positioned, not a search for any token.
    assert(AutoDxMessageParser::parse(QStringLiteral("C5R ON3CCM JO10"))
        .transmitter == QStringLiteral("ON3CCM"));
    assert(AutoDxMessageParser::parse(QStringLiteral("NH6WD W4IPC FN43"))
        .transmitter == QStringLiteral("W4IPC"));
    assert(AutoDxMessageParser::parse(QStringLiteral("VP2MAA RA3LD R-15"))
        .transmitter == QStringLiteral("RA3LD"));
    assert(AutoDxMessageParser::parse(QStringLiteral("CQ DX KP5/NP3VI FK68"))
        .transmitter == QStringLiteral("KP5/NP3VI"));
    assert(AutoDxMessageParser::parse(QStringLiteral("OM0RX <A1CALL> -10"))
        .transmitter == QStringLiteral("A1CALL"));
    assert(AutoDxMessageParser::parse(QStringLiteral("C5R <...> JO10"))
        .transmitter.isEmpty());
    assert(!AutoDxMessageParser::parse(QStringLiteral("C5R <...> JO10"))
        .senderResolved);
    assert(!AutoDxMessageParser::parse(QStringLiteral("ON3CCM C5R CQ"))
        .isCq);
    const AutoDxParsedMessage rr73 = AutoDxMessageParser::parse(
        QStringLiteral("OM0RX RA3WY RR73"));
    assert(rr73.isExchangeOnly && rr73.isTerminalAcknowledgement);
    const AutoDxParsedMessage rrr = AutoDxMessageParser::parse(
        QStringLiteral("OM0RX RA3WY RRR"));
    assert(rrr.isExchangeOnly && !rrr.isTerminalAcknowledgement);
    assert(AutoDxMessageParser::parse(QStringLiteral("OM0RX RA3WY 73"))
        .isTerminalAcknowledgement);
    assert(!AutoDxMessageParser::parse(QStringLiteral("OM0RX RA3WY -11"))
        .isExchangeOnly);

    DxccTracker tracker;
    HvCty cty;
    TargetScorer scorer(&tracker, &cty);
    scorer.setUSGridOnly(false);
    scorer.setMyCallsign(QStringLiteral("OM0RX"));
    scorer.setTargetWeights(10000, 1000, 500, 400, 200, 10);

    QSet<QString> watchedDxpeditions;
    watchedDxpeditions.insert(QStringLiteral("BLOCK1@7"));
    scorer.setDxpeditionWatch(watchedDxpeditions, 12000);

    // Historical novelty is fail-closed until OM0RX reports an attested
    // Wavelog snapshot, including for directed callers.
    tracker.setCallStatus(QStringLiteral("BLOCK1"), true, true);
    tracker.setGridStatus(QStringLiteral("JN89"), true);
    ScoredTarget blocked = scorer.scoreTarget(
        decode(QStringLiteral("BLOCK1"), QStringLiteral("JN89AA"), QStringLiteral("CQ BLOCK1 JN89")));
    assert(blocked.priority == 0);
    assert(blocked.priorityReason == QStringLiteral("Wavelog history unavailable"));
    scorer.setHistoricalNoveltyAllowed(true);
    AutoDxSelectionConfig legacyScoring;
    legacyScoring.preferNonEurope = false;
    scorer.setSelectionConfig(legacyScoring);

    // Country exclusions are hard AutoDX eligibility gates. A band-specific
    // rule affects only that band; ALL applies to every band, including
    // directed callers and award/DXpedition candidates.
    QMap<int, QSet<QString> > excludedCountries;
    excludedCountries[7].insert(QStringLiteral("FIXTUREENTITY"));
    scorer.setExcludedCountriesByBand(excludedCountries);
    tracker.setCallStatus(QStringLiteral("EXCL30"), true, true);
    ScoredTarget excluded30m = scorer.scoreTarget(decode(
        QStringLiteral("EXCL30"), QStringLiteral("JN88AA"),
        QStringLiteral("CQ EXCL30 JN88")));
    assert(excluded30m.priority == 0);
    assert(excluded30m.priorityReason ==
           QStringLiteral("Country excluded on this band: Fixture Entity"));
    CachedDecode allowed20m = decode(QStringLiteral("ALLOW20"), QStringLiteral("JN88AA"),
                                     QStringLiteral("CQ ALLOW20 JN88"));
    allowed20m.bandIndex = 8;
    tracker.setCallStatus(QStringLiteral("ALLOW20"), true, true);
    assert(scorer.scoreTarget(allowed20m).priority > 0);
    excludedCountries.clear();
    excludedCountries[-1].insert(QStringLiteral("FIXTUREENTITY"));
    scorer.setExcludedCountriesByBand(excludedCountries);
    assert(scorer.scoreTarget(allowed20m).priority == 0);
    scorer.setExcludedCountriesByBand(QMap<int, QSet<QString> >());

    // A grid remains independently eligible even when its entity and band
    // slot are already worked.
    tracker.setCallStatus(QStringLiteral("GRID1"), false, false);
    tracker.setGridStatus(QStringLiteral("JN88"), true);
    ScoredTarget gridOnly = scorer.scoreTarget(
        decode(QStringLiteral("GRID1"), QStringLiteral("JN88AA"), QStringLiteral("CQ GRID1 JN88")));
    assert(!gridOnly.isNewDXCC);
    assert(!gridOnly.isNewBandSlot);
    assert(gridOnly.isNewGrid);
    assert(gridOnly.priority == 500);

    // Independent dimensions combine in the production scorer.
    tracker.setCallStatus(QStringLiteral("ALL1"), true, true);
    tracker.setGridStatus(QStringLiteral("FN31"), true);
    ScoredTarget all = scorer.scoreTarget(
        decode(QStringLiteral("ALL1"), QStringLiteral("FN31AA"), QStringLiteral("CQ ALL1 FN31")));
    assert(all.isNewDXCC && all.isNewBandSlot && all.isNewGrid);
    assert(all.priority == 11500);
    AwardHuntingConfig maxOnlyAwards;
    maxOnlyAwards.stackScores = false;
    scorer.setAwardHuntingConfig(maxOnlyAwards);
    assert(scorer.scoreTarget(
        decode(QStringLiteral("ALL1"), QStringLiteral("FN31AA"),
               QStringLiteral("ALL1 K1ZZ -15"))).priority == 10000);
    scorer.setAwardHuntingConfig(AwardHuntingConfig());

    // Outcome learning is bounded and can tune an already eligible target,
    // but it cannot create eligibility on its own.
    QTemporaryDir outcomeDir;
    assert(outcomeDir.isValid());
    QFile outcomeFile(outcomeDir.path() + QStringLiteral("/outcomes.jsonl"));
    assert(outcomeFile.open(QIODevice::WriteOnly));
    const QByteArray outcomeJson(
        "{\"schema\":\"om0rx.autodx.outcome.v1\",\"call\":\"OUT1\","
        "\"outcome\":\"completed\"}\n");
    assert(outcomeFile.write(outcomeJson) == outcomeJson.size());
    outcomeFile.close();
    assert(scorer.loadOutcomeLearning(outcomeFile.fileName(), true));
    tracker.setCallStatus(QStringLiteral("OUT1"), true, false);
    tracker.setGridStatus(QStringLiteral("EM11"), false);
    assert(scorer.scoreTarget(decode(QStringLiteral("OUT1"), QStringLiteral("EM11AA"),
        QStringLiteral("OUT1 K1ZZ -15"))).priority == 10075);

    // Portable award references are an additional scoring dimension. They
    // can admit an otherwise ordinary new call, stack their independent gap
    // values, and remain subordinate to the exact call/band/mode guard.
    QTemporaryDir awardDir;
    assert(awardDir.isValid());
    QFile awardFile(awardDir.path() + QStringLiteral("/award_hunting.json"));
    assert(awardFile.open(QIODevice::WriteOnly));
    const QString now = QDateTime::currentDateTimeUtc().toString(Qt::ISODate);
    const QString expiry = QDateTime::currentDateTimeUtc().addSecs(600).toString(Qt::ISODate);
    const QByteArray awardJson = QString(
        "{\"schema\":1,\"history_authoritative\":true,\"activations\":[{"
        "\"callsign\":\"REF1\",\"program\":\"POTA\",\"reference\":\"K-0001\","
        "\"band\":\"30m\",\"mode\":\"FT8\",\"spotted_at_utc\":\"%1\","
        "\"expires_at_utc\":\"%2\",\"slot_key\":\"POTA:K-0001@30m@FT8\",\"history_status\":\"authoritative\"," 
        "\"gaps\":{\"new_reference\":true,\"new_reference_on_band\":true,"
        "\"new_reference_on_band_mode\":true}},{"
        "\"callsign\":\"REF1\",\"program\":\"SOTA\",\"reference\":\"W1/AA-001\"," 
        "\"band\":\"30m\",\"mode\":\"FT8\",\"spotted_at_utc\":\"%1\"," 
        "\"expires_at_utc\":\"%2\",\"slot_key\":\"SOTA:W1/AA-001@30m@FT8\",\"history_status\":\"authoritative\"," 
        "\"gaps\":{\"new_reference\":true,\"new_reference_on_band\":false,"
        "\"new_reference_on_band_mode\":false}}]}").arg(now, expiry).toUtf8();
    assert(awardFile.write(awardJson) == awardJson.size());
    awardFile.close();
    assert(scorer.loadAwardActivationIndex(awardFile.fileName()));
    tracker.setCallStatus(QStringLiteral("REF1"), false, false);
    tracker.setGridStatus(QStringLiteral("EM10"), false);
    ScoredTarget referenceOnly = scorer.scoreTarget(decode(
        QStringLiteral("REF1"), QStringLiteral("EM10AA"), QStringLiteral("CQ POTA REF1 EM10")));
    assert(referenceOnly.isAwardReference
           && referenceOnly.awardProgram == QStringLiteral("POTA+SOTA"));
    assert(referenceOnly.awardReference == QStringLiteral("K-0001,W1/AA-001"));
    assert(referenceOnly.awardReferences.size() == 2);
    const QString selectedAdif = AwardAdifPolicy::adifFields(
        referenceOnly.awardReferences);
    assert(selectedAdif.contains(QStringLiteral("<POTA_REF:6>K-0001")));
    assert(selectedAdif.contains(QStringLiteral("<SOTA_REF:9>W1/AA-001")));
    assert(referenceOnly.priority == (1800 + 2500 + 1000 + 500)
        + (1800 + 2500));
    tracker.setCallWorkedSlot(QStringLiteral("REF1"), true);
    assert(scorer.scoreTarget(decode(QStringLiteral("REF1"), QStringLiteral("EM10AA"),
        QStringLiteral("CQ POTA REF1 EM10"))).priority == 0);

    // Direct calls are independently eligible through the calling-me weight.
    tracker.setCallStatus(QStringLiteral("A1CALL"), false, false);
    tracker.setGridStatus(QStringLiteral("JO40"), false);
    ScoredTarget calling = scorer.scoreTarget(
        decode(QStringLiteral("A1CALL"), QStringLiteral("JO40AA"), QStringLiteral("OM0RX A1CALL -10")));
    assert(calling.isCallingMe);
    assert(calling.priority == 400);

    // Exchange-only replies belong to an existing QSO. They must never be
    // re-admitted as fresh directed callers after queue ownership is lost,
    // otherwise AutoDX restarts at the report stage (the RA3WY regression).
    tracker.setCallStatus(QStringLiteral("RA3WY"), true, true);
    const QStringList exchangeOnlyMessages = QStringList()
        << QStringLiteral("OM0RX RA3WY RRR")
        << QStringLiteral("OM0RX RA3WY RR73")
        << QStringLiteral("OM0RX RA3WY 73");
    for (const QString &message : exchangeOnlyMessages) {
        ScoredTarget exchangeOnly = scorer.scoreTarget(decode(
            QStringLiteral("RA3WY"), QStringLiteral("KO81AA"), message));
        assert(!exchangeOnly.isCallingMe);
        assert(exchangeOnly.priority == 0);
        assert(exchangeOnly.priorityReason ==
               QStringLiteral("Exchange-only reply is not a new caller"));
    }

    // A pending Wavelog acknowledgement blocks even a directed caller.  This
    // closes the interval between local logging and authoritative history
    // hydration without creating a duplicate QSO.
    QSet<QString> pendingCalls;
    pendingCalls.insert(QStringLiteral("A1CALL"));
    scorer.setPendingWavelogCalls(pendingCalls);
    CachedDecode weakWorkedCaller = decode(
        QStringLiteral("A1CALL"), QStringLiteral("JO40AA"),
        QStringLiteral("OM0RX A1CALL -24"));
    weakWorkedCaller.snr = -24;
    ScoredTarget priorityCaller = scorer.scoreTarget(weakWorkedCaller);
    assert(priorityCaller.isCallingMe);
    assert(priorityCaller.priority == 0);
    assert(priorityCaller.priorityReason == QStringLiteral("Wavelog acknowledgement pending"));
    pendingCalls.clear();
    scorer.setPendingWavelogCalls(pendingCalls);

    // CQ/SNR alone never turns a fully-worked random station into a target.
    tracker.setCallStatus(QStringLiteral("WORKED1"), false, false);
    tracker.setCallWorkedSlot(QStringLiteral("WORKED1"), true);
    tracker.setGridStatus(QStringLiteral("JO50"), false);
    CachedDecode worked = decode(
        QStringLiteral("WORKED1"), QStringLiteral("JO50AA"), QStringLiteral("CQ WORKED1 JO50"));
    worked.isCQ = true;
    worked.snr = 0;
    ScoredTarget excluded = scorer.scoreTarget(worked);
    assert(excluded.priority == 0);
    QList<CachedDecode> candidates;
    candidates << worked;
    assert(scorer.scoreAllTargets(candidates).isEmpty());

    // Permanent duplicate policy is exact per call/band/mode.  Once the
    // Wavelog-backed slot says worked, even a direct call and a new grid are
    // ineligible on this slot.
    tracker.setCallStatus(QStringLiteral("A1DUPE"), false, false);
    tracker.setCallWorkedSlot(QStringLiteral("A1DUPE"), true);
    tracker.setGridStatus(QStringLiteral("FN20"), true);
    ScoredTarget directedDupe = scorer.scoreTarget(
        decode(QStringLiteral("A1DUPE"), QStringLiteral("FN20AA"),
               QStringLiteral("OM0RX A1DUPE -05")));
    assert(directedDupe.isCallingMe);
    assert(directedDupe.priority == 0);
    assert(directedDupe.priorityReason
        == QStringLiteral("Call already worked on this band/mode"));

    // Pending outbox identities are negative-only inhibition: they do not
    // become worked history, but the same call cannot be selected again.
    pendingCalls.clear();
    pendingCalls.insert(QStringLiteral("ALL1"));
    scorer.setPendingWavelogCalls(pendingCalls);
    ScoredTarget pending = scorer.scoreTarget(
        decode(QStringLiteral("ALL1"), QStringLiteral("FN31AA"), QStringLiteral("CQ ALL1 FN31")));
    assert(pending.priority == 0);
    assert(pending.priorityReason == QStringLiteral("Wavelog acknowledgement pending"));

    // Pending inhibition is portable/base-call symmetric.
    pendingCalls.clear();
    pendingCalls.insert(QStringLiteral("NP3VI"));
    scorer.setPendingWavelogCalls(pendingCalls);
    assert(scorer.isPendingWavelogCall(QStringLiteral("KP5/NP3VI")));
    assert(scorer.scoreTarget(
        decode(QStringLiteral("KP5/NP3VI"), QStringLiteral("FK68AA"),
               QStringLiteral("CQ KP5/NP3VI FK68"))).priority == 0);
    pendingCalls.clear();
    pendingCalls.insert(QStringLiteral("KP5/NP3VI"));
    scorer.setPendingWavelogCalls(pendingCalls);
    assert(scorer.isPendingWavelogCall(QStringLiteral("NP3VI")));
    assert(scorer.scoreTarget(
        decode(QStringLiteral("NP3VI"), QStringLiteral("FK68AA"),
               QStringLiteral("CQ NP3VI FK68"))).priority == 0);

    pendingCalls.clear();
    scorer.setPendingWavelogCalls(pendingCalls);

    // Operator may select last-decoded ordering instead of score ordering.
    tracker.setCallStatus(QStringLiteral("HIGH1"), true, false);
    tracker.setGridStatus(QStringLiteral("JN70"), false);
    tracker.setCallStatus(QStringLiteral("LATE1"), false, false);
    tracker.setGridStatus(QStringLiteral("JN71"), true);
    CachedDecode high = decode(QStringLiteral("HIGH1"), QStringLiteral("JN70AA"),
                               QStringLiteral("CQ HIGH1 JN70"));
    CachedDecode late = decode(QStringLiteral("LATE1"), QStringLiteral("JN71AA"),
                               QStringLiteral("CQ LATE1 JN71"));
    high.timestamp = QDateTime::fromMSecsSinceEpoch(1000, Qt::UTC);
    late.timestamp = QDateTime::fromMSecsSinceEpoch(2000, Qt::UTC);
    AutoDxSelectionConfig ordering;
    ordering.selectionOrder = QStringLiteral("last");
    scorer.setSelectionConfig(ordering);
    assert(scorer.getBestTarget(QList<CachedDecode>() << high << late).callsign == QStringLiteral("LATE1"));
    ordering.selectionOrder = QStringLiteral("score");
    scorer.setSelectionConfig(ordering);
    assert(scorer.getBestTarget(QList<CachedDecode>() << high << late).callsign == QStringLiteral("HIGH1"));

    // WSJT-Z-compatible matrix categories, non-Europe preference and 73-as-CQ
    // are applied natively. The external metadata never supplies eligibility.
    AutoDxEligibilityFacts nonEurope;
    nonEurope.newCall = true;
    nonEurope.bandCall = true;
    nonEurope.continent = QStringLiteral("AS");
    tracker.setEligibilityFacts(QStringLiteral("AS1AA"), nonEurope);
    tracker.setCallStatus(QStringLiteral("AS1AA"), false, false);
    tracker.setGridStatus(QStringLiteral("PM95"), false);
    AutoDxSelectionConfig matrix;
    matrix.filterMatrixEnabled = true;
    matrix.filterNewCall = true;
    matrix.filterBandCall = false;
    matrix.filterBandGrid = false;
    matrix.preferNonEurope = true;
    matrix.treat73AsCq = true;
    scorer.setSelectionConfig(matrix);
    ScoredTarget preferred = scorer.scoreTarget(decode(
        QStringLiteral("AS1AA"), QStringLiteral("PM95AA"),
        QStringLiteral("AS1AA K1ZZ 73")));
    assert(preferred.priority == 2000 + 7500 + 200);
    assert(preferred.priorityReason.contains(QStringLiteral("non-europe-preference")));

    AutoDxSelectionConfig matrixAward = matrix;
    matrixAward.filterNewCall = false;
    matrixAward.filterNewDxcc = true;
    matrixAward.preferNonEurope = false;
    scorer.setSelectionConfig(matrixAward);
    AwardHuntingConfig campaignAwards;
    campaignAwards.newDxccWeight = 1234;
    campaignAwards.dxccWeightPercent = 200;
    scorer.setAwardHuntingConfig(campaignAwards);
    AutoDxEligibilityFacts matrixAwardFacts;
    matrixAwardFacts.newDxcc = true;
    matrixAwardFacts.bandCall = true;
    matrixAwardFacts.continent = QStringLiteral("EU");
    tracker.setEligibilityFacts(QStringLiteral("MX1"), matrixAwardFacts);
    tracker.setCallStatus(QStringLiteral("MX1"), true, false);
    tracker.setGridStatus(QStringLiteral("MX1GRID"), false);
    assert(scorer.scoreTarget(decode(QStringLiteral("MX1"), QStringLiteral("JO20AA"),
        QStringLiteral("MX1 K1ZZ -15"))).priority == 2468);
    scorer.setAwardHuntingConfig(AwardHuntingConfig());
    scorer.setSelectionConfig(matrix);

    // LoTW-only is conditional on data availability.
    matrix.lotwOnly = true;
    scorer.setSelectionConfig(matrix);
    scorer.setLotwMembership(QSet<QString>(), false);
    assert(scorer.scoreTarget(decode(QStringLiteral("AS1AA"), QStringLiteral("PM95AA"),
                                     QStringLiteral("CQ AS1AA PM95"))).priority > 0);
    scorer.setLotwMembership(QSet<QString>(), true);
    assert(scorer.scoreTarget(decode(QStringLiteral("AS1AA"), QStringLiteral("PM95AA"),
                                     QStringLiteral("CQ AS1AA PM95"))).priority == 0);

    // Catalogue "any active" broadens DXCC need only while the Wavelog-backed
    // call/band fact is still new. Needed-only and already-worked-on-band both
    // remain ineligible.
    scorer.setLotwMembership(QSet<QString>(), false);
    AutoDxEligibilityFacts expeditionFacts;
    expeditionFacts.bandCall = true;
    expeditionFacts.continent = QStringLiteral("AS");
    tracker.setEligibilityFacts(QStringLiteral("EXP1"), expeditionFacts);
    tracker.setCallStatus(QStringLiteral("EXP1"), false, false);
    tracker.setGridStatus(QStringLiteral("PM97"), false);
    watchedDxpeditions.clear();
    watchedDxpeditions.insert(QStringLiteral("EXP1@7"));
    scorer.setDxpeditionWatch(watchedDxpeditions, 12000);
    scorer.setDxpeditionPolicy(true, false);
    assert(scorer.scoreTarget(decode(QStringLiteral("EXP1"), QStringLiteral("PM97AA"),
                                     QStringLiteral("CQ EXP1 PM97"))).priority == 0);
    scorer.setDxpeditionPolicy(true, true);
    ScoredTarget anyActive = scorer.scoreTarget(decode(
        QStringLiteral("EXP1"), QStringLiteral("PM97AA"),
        QStringLiteral("CQ EXP1 PM97")));
    assert(anyActive.priority >= 12000);
    assert(anyActive.priorityReason.contains(QStringLiteral("active-dxpedition-any-active")));
    expeditionFacts.bandCall = false;
    tracker.setEligibilityFacts(QStringLiteral("EXP1"), expeditionFacts);
    assert(scorer.scoreTarget(decode(QStringLiteral("EXP1"), QStringLiteral("PM97AA"),
                                     QStringLiteral("CQ EXP1 PM97"))).priority == 0);
    scorer.setDxpeditionPolicy(true, false);

    // Neither preference nor catalog boosts may resurrect a matrix-blocked
    // target, even when new-call metadata would otherwise match.
    AutoDxEligibilityFacts blockedFacts = nonEurope;
    tracker.setEligibilityFacts(QStringLiteral("BLOCK2"), blockedFacts);
    tracker.setCallStatus(QStringLiteral("BLOCK2"), false, false);
    tracker.setGridStatus(QStringLiteral("PM96"), false);
    watchedDxpeditions.clear();
    watchedDxpeditions.insert(QStringLiteral("BLOCK2@7"));
    scorer.setDxpeditionWatch(watchedDxpeditions, 12000);
    matrix.lotwOnly = false;
    matrix.enabledContinents.remove(QStringLiteral("NA"));
    scorer.setSelectionConfig(matrix);
    ScoredTarget matrixBlocked = scorer.scoreTarget(decode(
        QStringLiteral("BLOCK2"), QStringLiteral("PM96AA"),
        QStringLiteral("CQ BLOCK2 PM96")));
    assert(matrixBlocked.priority == 0);
    assert(matrixBlocked.priorityReason.contains(QStringLiteral("continent-disabled")));

    // Full hunting admits a different call from a DXCC whose exact band/mode
    // slot is still unconfirmed.
    scorer.setSelectionConfig(AutoDxSelectionConfig());
    scorer.setConfirmedDxccEntities(QSet<QString>(), true);
    scorer.setFullHuntingMode(true);
    AutoDxEligibilityFacts confirmationFacts;
    confirmationFacts.newCall = true;
    confirmationFacts.bandCall = true;
    confirmationFacts.continent = QStringLiteral("EU");
    tracker.setEligibilityFacts(QStringLiteral("HUNT1"), confirmationFacts);
    tracker.setCallStatus(QStringLiteral("HUNT1"), false, false);
    tracker.setGridStatus(QStringLiteral("JN89"), false);
    tracker.setConfirmationStatus(QStringLiteral("HUNT1"), true, false);
    ScoredTarget huntingSlot = scorer.scoreTarget(decode(
        QStringLiteral("HUNT1"), QStringLiteral("JN89AA"),
        QStringLiteral("CQ HUNT1 JN89")));
    assert(huntingSlot.priority > 0 && huntingSlot.isUnconfirmedBandSlot);
    tracker.setConfirmationStatus(QStringLiteral("HUNT1"), true, true);
    assert(scorer.scoreTarget(decode(QStringLiteral("HUNT1"), QStringLiteral("JN89AA"),
        QStringLiteral("CQ HUNT1 JN89"))).priority == 0);

    // Full hunting is priority-first, not exclusive: when the operator's
    // matrix enables band-call fallback, an NB/NM call remains callable after
    // its DXCC band/mode slot is already confirmed.
    AutoDxSelectionConfig huntingMatrix;
    huntingMatrix.filterMatrixEnabled = true;
    huntingMatrix.filterNewCall = false;
    huntingMatrix.filterNewDxcc = false;
    huntingMatrix.filterNewGrid = false;
    huntingMatrix.filterBandCall = true;
    huntingMatrix.filterBandDxcc = false;
    huntingMatrix.filterBandGrid = false;
    scorer.setSelectionConfig(huntingMatrix);
    ScoredTarget huntingFallback = scorer.scoreTarget(decode(
        QStringLiteral("HUNT1"), QStringLiteral("JN89AA"),
        QStringLiteral("CQ HUNT1 JN89")));
    assert(huntingFallback.priority > 0);
    assert(huntingFallback.eligibilityClass == QStringLiteral("band-call"));
    scorer.setFullHuntingMode(false);

    assert(tracker.dxccQueries >= 4);
    assert(tracker.bandQueries >= 4);
    assert(tracker.gridQueries >= 4);

    // Non-gating microbenchmark: both paths run the production scorer, but
    // getBestTarget should avoid materializing and stable-sorting all rows.
    AutoDxSelectionConfig benchmarkConfig;
    benchmarkConfig.preferNonEurope = false;
    benchmarkConfig.selectionOrder = QStringLiteral("score");
    scorer.setSelectionConfig(benchmarkConfig);
    QList<CachedDecode> benchmarkDecodes;
    for (int i = 0; i < 8000; ++i) {
        const QString call = QStringLiteral("B%1AA").arg(i);
        tracker.setCallStatus(call, true, false);
        CachedDecode item = decode(call, QStringLiteral("JN88AA"),
                                   QStringLiteral("CQ ") + call + QStringLiteral(" JN88"));
        item.timestamp = QDateTime::fromMSecsSinceEpoch(i, Qt::UTC);
        benchmarkDecodes.append(item);
    }
    QElapsedTimer benchmarkTimer;
    benchmarkTimer.start();
    const QList<ScoredTarget> sortedBenchmark = scorer.scoreAllTargets(benchmarkDecodes);
    const qint64 sortMicros = benchmarkTimer.nsecsElapsed() / 1000;
    benchmarkTimer.restart();
    const ScoredTarget bestBenchmark = scorer.getBestTarget(benchmarkDecodes);
    const qint64 bestMicros = benchmarkTimer.nsecsElapsed() / 1000;
    assert(sortedBenchmark.size() == benchmarkDecodes.size());
    assert(!bestBenchmark.callsign.isEmpty());
    QTextStream(stdout) << "decode-selection-benchmark candidates=8000 full-sort-us="
                        << sortMicros << " one-pass-us=" << bestMicros << Qt::endl;
    // Ranking cannot let repeated-decoding/reference bonuses displace ATNO
    // or band-slot value. Operator's explicit newest-first order still works.
    ScoredTarget atno, slot, bonus, caller;
    atno.isNewDXCC = true; atno.priority = 10000;
    slot.isNewBandSlot = true; slot.priority = 1000;
    bonus.isAwardReference = true; bonus.priority = 999999;
    caller.isCallingMe = true; caller.priority = 400;
    assert(atno.preferredTo(slot, false));
    assert(slot.preferredTo(bonus, false));
    assert(caller.preferredTo(atno, false));
    bonus.decodedAt = QDateTime::currentDateTimeUtc();
    atno.decodedAt = bonus.decodedAt.addSecs(-15);
    assert(bonus.preferredTo(atno, true));
    return 0;
}
