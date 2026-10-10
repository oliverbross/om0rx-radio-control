#include <QApplication>
#include <QDir>
#include <QFile>
#include <QTemporaryDir>
#include <QSettings>
#include <cassert>

#define private public
#include "HvAutoDxer/autodxercore.h"
#undef private
#include "HvAutoDxer/autodxruntimeconfig.h"
#include "HvDecodeList/hvcty.h"
#include "HvDxccTracker/hvdxcctracker.h"
#include "HvTxW/hvmultianswermodw.h"

static void writeFixture(const QString &path, const QByteArray &data)
{
    QFile file(path);
    assert(file.open(QIODevice::WriteOnly));
    assert(file.write(data) == data.size());
}

static void armCrossBand(AutoDxerCore &core, const QString &call)
{
    core.m_pendingCrossBandCallsign = call;
    core.m_pendingCrossBandSource = "RBN";
    core.m_pendingCrossBandReason = "new-dxcc";
    core.m_pendingCrossBandBand = 11;
    core.m_pendingCrossBandReturnBand = 6;
    core.m_pendingCrossBandDialFreq = 24915000;
    core.m_pendingCrossBandAudioFreq = 1000;
}

static void addCrossBandAlert(AutoDxerCore &core, const QString &call, int band,
                              int offsetHz = 1000)
{
    ExternalSpot spot;
    spot.callsign = call;
    spot.bandIndex = band;
    spot.frequencyHz = core.m_bandManager->bandFrequencyHz(band) + offsetHz;
    spot.mode = "FT8";
    spot.source = "RBN";
    spot.spotter = "K1TEST";
    spot.spotterCount = 1;
    spot.spotters << spot.spotter;
    core.m_spotAggregator->addLocalSpot(spot);
}

static QStringList localDecode(const QString &message, int snr = -10,
                               int audioFrequency = 1200)
{
    QStringList row;
    row << "120000" << QString::number(snr) << "0.1" << "1200"
        << message << "Fixture" << "9999" << QString::number(audioFrequency);
    return row;
}

int main(int argc, char **argv)
{
    QApplication application(argc, argv);
    QTemporaryDir settings;
    assert(settings.isValid());
    QDir().mkpath(settings.path() + "/settings/database");
    writeFixture(settings.path() + "/settings/database/cty.dat",
                 "Country A: 1: 1: EU: 0: 0: 0: A: A,AA,=A1EX;\n"
                 "Country B: 2: 2: AF: 0: 0: 0: B: B,BB,=B1EX;\n");
    writeFixture(settings.path() + "/settings/database/dxcc_numbers.dat", "A:1\nB:2\n");
    {
        QSettings config(settings.path() + "/settings/autodx.ini", QSettings::IniFormat);
        const QTime now = QTime::currentTime();
        config.setValue("BandSelection/EnabledBands", "3,6,8");
        config.setValue("BandSwitching/Enabled", true);
        config.setValue("BandSchedules/Band4Restricted", false);
        config.setValue("BandSchedules/Band6Restricted", true);
        config.setValue("BandSchedules/Band6Start", now.addSecs(3600).toString("HH:mm"));
        config.setValue("BandSchedules/Band6End", now.addSecs(7200).toString("HH:mm"));
        config.sync();
    }
    HvCty cty(0);
    AutoDxerCore core(&cty, settings.path() + "/settings");
    core.setCallsign("OM0RX");
    HvDxccTracker tracker(settings.path());
    assert(tracker.initDatabase());
    core.setHvDxccTracker(&tracker);
    if (core.m_historyTimer) core.m_historyTimer->stop();
    if (core.m_recentlyWorkedCleanupTimer) core.m_recentlyWorkedCleanupTimer->stop();

    // FT4 is a first-class planner mode: its native 7.5-second cadence uses
    // a shorter debounce, mode evidence propagates through local spots and
    // award scoring, and band QSYs use FT4 dial frequencies.
    core.setCurrentMode("FT4");
    assert(core.decodePeriodDebounceSeconds() == 6);
    const QMap<int, int> ft4Dial = {
        {3, 1840000}, {4, 3575000}, {6, 7047000}, {7, 10140000},
        {8, 14080000}, {9, 18104000}, {10, 21140000},
        {11, 24919000}, {12, 28180000}, {14, 50318000}
    };
    for (auto it = ft4Dial.constBegin(); it != ft4Dial.constEnd(); ++it)
        assert(core.m_bandManager->bandFrequencyHz(it.key()) == it.value());
    assert(core.m_localSpotBridge->m_mode == "FT4");
    assert(core.m_spotAggregator->mode() == "FT4");
    assert(core.m_spotAggregator->dxClusterClient()->mode() == "FT4");
    assert(core.m_targetScorer->m_currentMode == "FT4");
    core.m_decodeCache->addDecode("B1MODE", "BB00", "Country B",
                                  "CQ B1MODE BB00", 8, 1200, 14080000, -5, true);
    armCrossBand(core, "B1MODE");
    core.m_pendingNonStdCallsign = "B1MODE";
    core.m_pendingSlotAnalysisTarget.callsign = "B1MODE";
    core.m_waitingForSlotAnalysis = true;
    core.setCurrentMode("FT8");
    assert(core.decodePeriodDebounceSeconds() == 12);
    assert(core.m_bandManager->bandFrequencyHz(8) == 14074000);
    assert(core.m_decodeCache->count() == 0);
    assert(core.m_pendingCrossBandCallsign.isEmpty());
    assert(core.m_pendingNonStdCallsign.isEmpty());
    assert(!core.m_waitingForSlotAnalysis);

    int dialChanges = 0;
    int txFrequencyChanges = 0;
    int bandChanges = 0;
    int requestedBand = -1;
    int emptyTargetChanges = 0;
    QObject::connect(&core, &AutoDxerCore::requestDialFreqChange,
                     [&](int) { ++dialChanges; });
    QObject::connect(&core, &AutoDxerCore::requestTxFreqChange,
                     [&](double) { ++txFrequencyChanges; });
    QObject::connect(&core, &AutoDxerCore::requestBandChange,
                     [&](int band) { ++bandChanges; requestedBand = band; });
    QObject::connect(&core, &AutoDxerCore::targetChanged,
                     [&](const DxTarget &target) {
                         if (!target.isValid()) ++emptyTargetChanges;
                     });

    // Pending cross-band verification is visible in native read-only status
    // and all identifying evidence clears through the canonical lifecycle.
    armCrossBand(core, "B1TELEM");
    core.m_pendingCrossBandTime = QDateTime::currentDateTimeUtc();
    QJsonObject verification = core.autoDxStatus()
        .value("pending_verification").toObject();
    assert(verification.value("active").toBool());
    assert(verification.value("callsign").toString() == "B1TELEM");
    assert(verification.value("band_index").toInt() == 11);
    assert(verification.value("source").toString() == "RBN");
    assert(verification.value("reason").toString() == "new-dxcc");
    core.clearPendingCrossBandVerification();
    verification = core.autoDxStatus().value("pending_verification").toObject();
    assert(!verification.value("active").toBool());
    assert(verification.value("callsign").toString().isEmpty());
    assert(verification.value("source").toString().isEmpty());
    assert(verification.value("reason").toString().isEmpty());

    // Retry/backoff and schedule filtering happen before band fairness. A
    // skipped candidate cannot advance the cursor or suppress another band.
    core.m_crossBandAlertCursorBand = 3;
    core.m_crossBandRetryAfter.insert(
        core.crossBandRetryKey("B1BUSY", 3),
        QDateTime::currentDateTimeUtc().addSecs(120));
    assert(core.crossBandRetryDeferred("B1BUSY", 3,
                                      QDateTime::currentDateTimeUtc()));
    assert(!core.crossBandRetryDeferred("B1OTHER", 8,
                                       QDateTime::currentDateTimeUtc()));
    assert(AutoDxCrossBandFairness::chooseBand(QList<int>() << 8 << 10,
                                               core.m_crossBandAlertCursorBand) == 8);
    assert(core.m_crossBandAlertCursorBand == 3);
    core.m_crossBandRetryAfter.clear();

    // Exercise the real planner path: several continuously fresh 80m calls
    // still occupy one band-level turn, the configured closed 40m schedule is
    // excluded, and later eligible bands receive the following turns.
    core.m_enabled = true;
    core.m_bandSwitchingEnabled = true;
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    core.m_state = AutoDxerCore::Listening;
    core.m_targetRespondedToUs = false;
    core.setCurrentBand(11);
    core.m_bandManager->setEnabledBands(QList<int>() << 4 << 6 << 8 << 10 << 11);
    core.m_crossBandAlertCursorBand = -1;
    core.m_bandSwitchCooldownSeconds = 0;
    core.m_lastBandSwitchTime = QDateTime();
    addCrossBandAlert(core, "B1LOWA", 4);
    addCrossBandAlert(core, "B1LOWB", 4);
    addCrossBandAlert(core, "B1LOWC", 4);
    addCrossBandAlert(core, "B1CLOSED", 6);
    addCrossBandAlert(core, "B1MID", 8);
    addCrossBandAlert(core, "B1HIGH", 10);

    // A locally heard eligible station gets the first admission pass. A
    // lower-class external alert cannot steal CAT before that reservation.
    core.m_decodeCache->addDecode("B1LOCAL", "BB00", "Country B",
                                  "CQ B1LOCAL BB00", 11, 1350,
                                  core.m_bandManager->bandFrequencyHz(11), -5, true);
    core.m_slotFinder->clearData();
    const int beforeLocalPriority = bandChanges;
    core.onDecodeComplete(false, 0);
    assert(core.m_waitingForSlotAnalysis);
    assert(core.m_pendingSlotAnalysisTarget.callsign == "B1LOCAL");
    assert(bandChanges == beforeLocalPriority);
    // A top-ranked station waiting for retry must not starve other callers.
    core.m_waitingForSlotAnalysis = false;
    core.m_pendingSlotAnalysisTarget = ScoredTarget();
    core.m_targetRetryAfter.insert(core.targetScopeKey("B1LOCAL", 11, "FT8"),
                                   QDateTime::currentDateTimeUtc().addSecs(120));
    core.m_decodeCache->addDecode("B1READY", "BB00", "Country B",
                                  "CQ B1READY BB00", 11, 1350,
                                  core.m_bandManager->bandFrequencyHz(11), -15, true);
    core.evaluateTargets();
    assert(core.m_waitingForSlotAnalysis);
    assert(core.m_pendingSlotAnalysisTarget.callsign == "B1READY");
    core.m_targetRetryAfter.clear();
    core.m_waitingForSlotAnalysis = false;
    core.m_pendingSlotAnalysisTarget = ScoredTarget();
    core.m_decodeCache->clear();

    const int beforeFairness = bandChanges;
    core.checkCrossBandAlerts();
    assert(bandChanges == beforeFairness + 1 && requestedBand == 4);
    assert(core.m_crossBandAlertCursorBand == 4);
    core.onBandChangeFailed(requestedBand, "fixture fairness first cleanup");
    core.m_lastBandSwitchTime = QDateTime();
    core.checkCrossBandAlerts();
    assert(requestedBand == 8); // closed band 6 cannot consume a turn
    assert(core.m_crossBandAlertCursorBand == 8);
    core.onBandChangeFailed(requestedBand, "fixture fairness second cleanup");
    core.m_lastBandSwitchTime = QDateTime();
    core.checkCrossBandAlerts();
    assert(requestedBand == 10);
    assert(core.m_crossBandAlertCursorBand == 10);
    core.onBandChangeFailed(requestedBand, "fixture fairness third cleanup");

    // A saved-origin return owns the single native CAT command slot. While
    // that band QSY is unresolved, neither another cross-band candidate nor a
    // same-band off-standard candidate may overwrite it. After deterministic
    // failure cleanup the off-standard evidence remains fresh and is
    // reconsidered normally.
    core.setCurrentBand(11);
    armCrossBand(core, "B1RETURN");
    const int beforeReturn = bandChanges;
    assert(core.returnFromPendingCrossBandVerification("fixture overlap return"));
    assert(bandChanges == beforeReturn + 1 && requestedBand == 6);
    assert(core.m_bandChangePending);
    assert(core.m_pendingCrossBandCallsign.isEmpty());
    MultiAnswerModW overlapQueue(false);
    core.setQueueWidget(&overlapQueue);
    core.m_slotFinder->clearData();
    core.m_decodeCache->addDecode("B1STANDARD", "BB00", "Country B",
                                  "CQ B1STANDARD BB00", 11, 1400,
                                  core.m_bandManager->bandFrequencyHz(11), -5, true);
    ScoredTarget standardTarget;
    standardTarget.callsign = "B1STANDARD";
    standardTarget.grid = "BB00";
    standardTarget.dxccEntity = "Country B";
    standardTarget.bandIndex = 11;
    standardTarget.audioFrequency = 1400;
    standardTarget.dialFrequencyHz = core.m_bandManager->bandFrequencyHz(11);
    standardTarget.snr = -5;
    standardTarget.priority = 10000;
    standardTarget.isNewDXCC = true;

    // Direct feed, ordinary evaluation/slot reservation and directed-caller
    // preemption are all ownership boundaries and must defer to CAT.
    core.feedToQueue(standardTarget, true);
    core.evaluateTargets();
    assert(!core.m_currentTarget.isValid());
    assert(!core.m_waitingForSlotAnalysis);
    assert(overlapQueue.getQueueList()->FindCallOrBaseCallRow("B1STANDARD") < 0);
    CachedDecode overlapCaller;
    overlapCaller.callsign = "A1CAT";
    overlapCaller.grid = "AA00";
    overlapCaller.dxccEntity = "Country A";
    overlapCaller.originalMessage = "OM0RX A1CAT -05";
    overlapCaller.bandIndex = 11;
    overlapCaller.audioFrequency = 1250;
    overlapCaller.dialFrequencyHz = core.m_bandManager->bandFrequencyHz(11);
    overlapCaller.snr = -5;
    overlapCaller.isLocalDecode = true;
    overlapCaller.timestamp = QDateTime::currentDateTimeUtc();
    core.considerCallingMePreemption(overlapCaller);
    assert(!core.m_currentTarget.isValid());
    assert(core.m_suspendedTarget.callsign.isEmpty());

    SlotAnalysis overlapAnalysis;
    overlapAnalysis.suggestedFreq = 1777;
    overlapAnalysis.alternateFreq = 1888;
    overlapAnalysis.confidence = 1.0;
    overlapAnalysis.totalSlots = 10;
    overlapAnalysis.occupiedSlots = 2;
    overlapAnalysis.reason = "fixture CAT overlap";
    const int beforeOverlapTx = txFrequencyChanges;
    core.onSlotAnalysisReady(overlapAnalysis);
    assert(txFrequencyChanges == beforeOverlapTx);

    // Verification age is observed only after CAT cleanup; the pending return
    // cannot spuriously terminalize it using the stale logical band.
    core.m_pendingNonStdCallsign = "B1AGEDVERIFY";
    core.m_pendingNonStdDialFreq = core.m_bandManager->bandFrequencyHz(11) + 10000;
    core.m_pendingNonStdTime = QDateTime::currentDateTimeUtc().addSecs(-61);
    const QDateTime frozenVerificationTime = core.m_pendingNonStdTime;
    core.evaluateTargets();
    assert(core.m_pendingNonStdCallsign == "B1AGEDVERIFY");
    assert(core.m_pendingNonStdTime == frozenVerificationTime);

    addCrossBandAlert(core, "B1OFF", 11, 10000);
    const int beforeOverlapBands = bandChanges;
    const int beforeOverlapDial = dialChanges;
    core.checkCrossBandAlerts();
    core.checkSameBandNonStdFreqAlerts();
    assert(bandChanges == beforeOverlapBands);
    assert(dialChanges == beforeOverlapDial);
    assert(core.m_pendingNonStdCallsign == "B1AGEDVERIFY");
    core.onBandChangeFailed(requestedBand, "fixture return CAT failure cleanup");
    assert(!core.m_bandChangePending);

    // The retained standard decode is considered exactly once after cleanup
    // and reserves slot analysis. A fresh directed caller can then preempt
    // that reservation exactly once through the normal path.
    core.evaluateTargets();
    assert(core.m_pendingNonStdCallsign.isEmpty());
    assert(core.m_waitingForSlotAnalysis);
    assert(core.m_pendingSlotAnalysisTarget.callsign == "B1STANDARD");
    core.m_decodeCache->addDecode("A1CAT", "AA00", "Country A",
                                  overlapCaller.originalMessage, 11, 1250,
                                  core.m_bandManager->bandFrequencyHz(11), -5, false);
    const int attemptBeforeCaller = core.m_attemptSequence;
    core.considerCallingMePreemption(overlapCaller);
    assert(core.m_currentTarget.callsign == "A1CAT");
    assert(core.m_currentTarget.isCallingMe);
    assert(core.m_suspendedTarget.callsign == "B1STANDARD");
    assert(core.m_attemptSequence == attemptBeforeCaller + 1);
    core.considerCallingMePreemption(overlapCaller);
    assert(core.m_attemptSequence == attemptBeforeCaller + 1);
    core.terminalClearCurrentTarget("fixture CAT overlap cleanup", false);
    overlapQueue.clearBothLists();

    // End-to-end sender provenance: a directed message caches the transmitter,
    // never its destination. An unresolved FROM token creates no local proof,
    // and therefore cannot satisfy a pending external C5R verification.
    core.m_decodeCache->clear();
    core.setCurrentBand(11);
    armCrossBand(core, "C5R");
    core.m_pendingCrossBandTime = QDateTime::currentDateTimeUtc();
    core.onLocalDecode(localDecode("C5R <...> JO10"));
    core.evaluateTargets();
    assert(core.m_pendingCrossBandCallsign == "C5R");
    assert(!core.targetLocallyFresh("C5R", 11, 60));
    core.onLocalDecode(localDecode("C5R ON3CCM JO10"));
    core.evaluateTargets();
    assert(core.m_pendingCrossBandCallsign == "C5R");
    assert(core.targetLocallyFresh("ON3CCM", 11, 60));
    assert(!core.targetLocallyFresh("C5R", 11, 60));
    core.clearPendingCrossBandVerification();

    // A resolved real caller addressed to OM0RX flows through parser, scorer,
    // calling-me admission and the native queue under its sender identity.
    core.onLocalDecode(localDecode("OM0RX A1CALL -10"));
    assert(core.m_currentTarget.callsign == "A1CALL");
    assert(core.m_currentTarget.isCallingMe);
    assert(core.m_targetRespondedToUs);
    const int directedNow = overlapQueue.getNowList()->FindCallOrBaseCallRow("A1CALL");
    const int directedQueued = overlapQueue.getQueueList()->FindCallOrBaseCallRow("A1CALL");
    assert(directedNow >= 0 || directedQueued >= 0);
    const QString directedStage = directedNow >= 0
        ? overlapQueue.getNowList()->model.item(directedNow, 7)->text()
        : overlapQueue.getQueueList()->model.item(directedQueued, 7)->text();
    assert(directedStage == "2");
    assert(overlapQueue.getQueueList()->FindCallOrBaseCallRow("A1CALL") >= 0
        || overlapQueue.getNowList()->FindCallOrBaseCallRow("A1CALL") >= 0);
    core.terminalClearCurrentTarget("fixture sender provenance cleanup", false);
    overlapQueue.clearBothLists();

    // ER3ZW's genuine reply at the ordinary 120-second boundary receives a
    // renewable completion grace. The original attempt age must not terminate
    // a progressing QSO; only an idle progress lease expires it.
    core.m_engagedCompletionGraceSeconds = 60;
    core.m_decodeCache->addDecode("ER3ZW", "KN00", "Fixture DXCC",
                                  "CQ ER3ZW KN00", 11, 1300,
                                  core.m_bandManager->bandFrequencyHz(11), -8, true);
    ScoredTarget lateReplyTarget;
    lateReplyTarget.callsign = "ER3ZW";
    lateReplyTarget.grid = "KN00";
    lateReplyTarget.dxccEntity = "Fixture DXCC";
    lateReplyTarget.bandIndex = 11;
    lateReplyTarget.audioFrequency = 1300;
    lateReplyTarget.dialFrequencyHz = core.m_bandManager->bandFrequencyHz(11);
    lateReplyTarget.snr = -8;
    lateReplyTarget.priority = 10000;
    lateReplyTarget.isNewDXCC = true;
    core.feedToQueue(lateReplyTarget, true);
    assert(core.m_currentTarget.callsign == "ER3ZW");
    core.m_targetAttemptElapsedOffsetMs = 120000;
    core.m_targetAttemptTimer.restart();
    core.onLocalDecode(localDecode("OM0RX ER3ZW -12", -8, 1300));
    assert(core.m_targetRespondedToUs);
    core.onDecodeComplete(false, 0);
    assert(core.m_currentTarget.callsign == "ER3ZW");
    assert(core.autoDxStatus().value("budget").toObject()
        .value("completion_grace_active").toBool());
    core.m_targetAttemptElapsedOffsetMs = 180000;
    core.m_targetAttemptTimer.restart();
    core.m_lastMissedCycleCheck = QDateTime();
    core.onDecodeComplete(false, 0);
    assert(core.m_currentTarget.callsign == "ER3ZW");
    core.m_lastTargetProgressUtc = QDateTime::currentDateTimeUtc().addSecs(-61);
    core.m_lastMissedCycleCheck = QDateTime();
    core.onDecodeComplete(false, 0);
    assert(!core.m_currentTarget.isValid());
    assert(!core.m_targetRespondedToUs);
    overlapQueue.clearBothLists();
    core.setQueueWidget(nullptr);

    const int beforeReconsideredDial = dialChanges;
    core.checkSameBandNonStdFreqAlerts();
    assert(dialChanges == beforeReconsideredDial + 1);
    assert(core.m_pendingNonStdCallsign == "B1OFF");
    core.m_pendingNonStdCallsign.clear();
    core.m_pendingNonStdDialFreq = 0;
    core.m_pendingNonStdTime = QDateTime();
    core.m_spotAggregator->clearSpots();
    core.m_bandManager->setEnabledBands(QList<int>() << 3 << 6 << 8);
    core.m_enabled = false;
    core.setState(AutoDxerCore::Idle);
    core.m_quietBandTimer.invalidate();
    bandChanges = 0;
    requestedBand = -1;
    dialChanges = 0;
    txFrequencyChanges = 0;

    // Timing policy boundaries are exact and do not depend on wall-clock sleeps.
    assert(!AutoDxTimingPolicy::normalAttemptExpired(119999, 120));
    assert(AutoDxTimingPolicy::normalAttemptExpired(120000, 120));
    assert(!AutoDxTimingPolicy::normalAttemptExpired(239999, 240));
    assert(AutoDxTimingPolicy::normalAttemptExpired(240000, 240));
    assert(AutoDxTimingPolicy::alignToFt8SlotSeconds(31) == 45);
    assert(!AutoDxTimingPolicy::engagedCompletionExpired(179999, 120, 60));
    assert(AutoDxTimingPolicy::engagedCompletionExpired(180000, 120, 60));
    assert(!AutoDxTimingPolicy::quietBandExpired(299999, 300));
    assert(AutoDxTimingPolicy::quietBandExpired(300000, 300));
    assert(!AutoDxTimingPolicy::verificationExpired(59, 60));
    assert(AutoDxTimingPolicy::verificationExpired(60, 60));
    assert(AutoDxTimingPolicy::noveltyPersists(true, false, true, true, true, 3));
    assert(!AutoDxTimingPolicy::noveltyPersists(true, false, false, true, true, 3));
    assert(!AutoDxTimingPolicy::noveltyPersists(true, false, true, true, true, 2));
    assert(AutoDxTimingPolicy::noveltyPersists(false, true, true, true, true, 2));

    // Accepted targets own their full configured attempt even after the
    // selection freshness window closes. At the exact call boundary, stale
    // ownership clears and the quiet-band clock starts immediately.
    core.m_enabled = true;
    core.setCurrentBand(8);
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "B1FULL";
    core.m_currentTarget.bandIndex = 8;
    core.m_currentTargetIsATNO = false;
    core.m_currentTargetIsNewSlot = false;
    core.m_targetRespondedToUs = false;
    core.m_normalCallSeconds = 120;
    core.m_targetHeardFreshSeconds = 60;
    core.m_targetAttemptElapsedOffsetMs = 60000;
    core.m_targetAttemptTimer.start();
    core.m_lastMissedCycleCheck = QDateTime();
    core.m_decodeCache->clear();
    MultiAnswerModW *savedQueue = core.m_queueWidget;
    core.m_queueWidget = nullptr;
    core.onDecodeComplete(false, 0);
    assert(core.m_currentTarget.callsign == "B1FULL");
    assert(!core.m_quietBandTimer.isValid());
    core.m_targetAttemptElapsedOffsetMs = 120000;
    core.m_targetAttemptTimer.restart();
    core.m_lastMissedCycleCheck = QDateTime();
    core.onDecodeComplete(false, 0);
    assert(!core.m_currentTarget.isValid());
    assert(core.m_state == AutoDxerCore::Listening);
    assert(core.m_quietBandTimer.isValid());
    core.m_queueWidget = savedQueue;

    // A target admitted from a nearly-stale local decode still owns the full
    // configured attempt even when MSHV removes it from Now/Queue after the
    // decode has aged beyond the cache window. Reinsert from stored accepted
    // state at 61/120 seconds; expire exactly at the configured boundary.
    MultiAnswerModW ownershipQueue(false);
    core.setQueueWidget(&ownershipQueue);
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    core.m_decodeCache->clear();
    core.m_decodeCache->addDecode("B1AGED", "BB00", "Country B",
                                  "CQ B1AGED BB00", 8, 1350, 14074000, -7, true);
    const QString agedKey = core.m_decodeCache->makeKey("B1AGED", 8);
    core.m_decodeCache->m_cache[agedKey].timestamp = QDateTime::currentDateTimeUtc().addSecs(-59);
    ScoredTarget agedTarget;
    agedTarget.callsign = "B1AGED";
    agedTarget.grid = "BB00";
    agedTarget.dxccEntity = "Country B";
    agedTarget.bandIndex = 8;
    agedTarget.audioFrequency = 1350;
    agedTarget.dialFrequencyHz = 14074000;
    agedTarget.snr = -7;
    agedTarget.priority = 10000;
    agedTarget.isNewDXCC = false;
    core.m_normalCallSeconds = 120;
    core.m_targetHeardFreshSeconds = 60;
    core.feedToQueue(agedTarget, true);
    assert(core.m_currentTarget.callsign == "B1AGED");
    core.m_targetAttemptElapsedOffsetMs = 62000;
    core.m_targetAttemptTimer.restart();
    core.m_decodeCache->m_cache[agedKey].timestamp = QDateTime::currentDateTimeUtc().addSecs(-121);
    ownershipQueue.clearBothLists();
    core.checkQueueStatus();
    assert(core.m_currentTarget.callsign == "B1AGED");
    assert(ownershipQueue.getQueueList()->FindCallOrBaseCallRow("B1AGED") >= 0
        || ownershipQueue.getNowList()->FindCallOrBaseCallRow("B1AGED") >= 0);
    assert(!core.m_quietBandTimer.isValid());
    core.m_targetAttemptElapsedOffsetMs = 120000;
    core.m_targetAttemptTimer.restart();
    core.m_lastMissedCycleCheck = QDateTime();
    core.onDecodeComplete(false, 0);
    assert(!core.m_currentTarget.isValid());
    assert(core.m_quietBandTimer.isValid());
    ownershipQueue.clearBothLists();
    core.setQueueWidget(nullptr);

    // A trailing message from a recently worked direct caller must not reopen
    // that QSO. Once the recent-worked lease is absent, a genuine direct caller
    // preempts an unanswered chase immediately, but never an engaged exchange.
    // The interrupted chase resumes with its consumed attempt budget.
    MultiAnswerModW queue(false);
    core.setQueueWidget(&queue);
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "B1CHASE";
    core.m_currentTarget.grid = "BB00";
    core.m_currentTarget.dxccEntity = "Country B";
    core.m_currentTarget.bandIndex = 8;
    core.m_currentTarget.audioFrequency = 1100;
    core.m_currentTarget.dialFrequencyHz = 14074000;
    core.m_currentTarget.priority = 10000;
    core.m_currentTarget.isCallingMe = false;
    core.m_currentTargetIsATNO = true;
    core.m_currentTargetIsNewSlot = false;
    core.m_targetRespondedToUs = false;
    core.m_targetAttemptElapsedOffsetMs = 90000;
    core.m_targetAttemptTimer.start();
    core.m_pendingWavelogCalls.insert("A1CALL");
    core.m_targetScorer->setPendingWavelogCalls(core.m_pendingWavelogCalls);
    core.m_recentlyWorked.insert(core.workedSlotKey("A1CALL", 8, "FT8"));
    CachedDecode direct;
    direct.callsign = "A1CALL";
    direct.grid = "AA00";
    direct.dxccEntity = "Country A";
    direct.originalMessage = "OM0RX A1CALL -24";
    direct.bandIndex = 8;
    direct.audioFrequency = 1250;
    direct.dialFrequencyHz = 14074000;
    direct.snr = -24;
    direct.isLocalDecode = true;
    direct.timestamp = QDateTime::currentDateTimeUtc();
    core.m_decodeCache->addDecode("A1CALL", "AA00", "Country A",
                                  direct.originalMessage, 8, 1250, 14074000, -24, false);
    core.considerCallingMePreemption(direct);
    assert(core.m_currentTarget.callsign == "B1CHASE");
    core.m_recentlyWorked.remove(core.workedSlotKey("A1CALL", 8, "FT8"));
    core.m_pendingWavelogCalls.clear();
    core.m_targetScorer->setPendingWavelogCalls(core.m_pendingWavelogCalls);
    core.considerCallingMePreemption(direct);
    assert(core.m_currentTarget.callsign == "A1CALL");
    assert(core.m_currentTarget.isCallingMe);
    // The decode which caused directed-caller admission is already valid QSO
    // progress. Count it immediately so timeout/hunting cannot abandon the
    // exchange before the caller's next repeat.
    assert(core.m_targetRespondedToUs);
    assert(core.m_suspendedTarget.callsign == "B1CHASE");
    assert(core.m_suspendedTargetElapsedMs >= 90000);

    CachedDecode secondCaller = direct;
    secondCaller.callsign = "A1OTHER";
    secondCaller.originalMessage = "OM0RX A1OTHER -05";
    core.m_targetRespondedToUs = true;
    core.considerCallingMePreemption(secondCaller);
    assert(core.m_currentTarget.callsign == "A1CALL");

    core.m_targetRespondedToUs = false;
    core.abandonCurrentTarget("direct caller fixture timeout");
    assert(core.m_currentTarget.callsign == "B1CHASE");
    assert(!core.m_currentTarget.isCallingMe);
    assert(core.currentTargetAttemptElapsedMs() >= 90000);
    assert(core.currentTargetAttemptElapsedMs() < 120000);
    assert(core.m_suspendedTarget.callsign.isEmpty());
    core.abandonCurrentTarget("fixture cleanup");
    core.m_pendingWavelogCalls.clear();
    core.m_targetScorer->setPendingWavelogCalls(core.m_pendingWavelogCalls);
    core.m_recentlyWorked.clear();
    core.setQueueWidget(nullptr);

    // A normal unanswered target owns AUTO until the configured boundary,
    // then rotates. A fresh persistent new-DXCC target remains eligible for
    // reconsideration after rotation instead of being lost with the queue.
    int disableAutoRequests = 0;
    QObject::connect(&core, &AutoDxerCore::requestDisableAuto,
                     [&]() { ++disableAutoRequests; });

    // A successfully logged target remains owned during the two-pass receive
    // guard, then is released. If the same
    // worked station later calls us again it is allowed to engage, but a brief
    // FT8 StopAuto/StartAuto transition must not clear it.  A sustained
    // terminal AUTO-off edge releases that exact stale ownership once and
    // starts the quiet timer.  AUTO-on remains authoritative protection for
    // an active exchange.
    core.m_enabled = true;
    core.setCurrentBand(8);
    core.clearSuspendedTarget();
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "A1DONE";
    core.m_currentTarget.bandIndex = 8;
    core.m_currentTarget.isCallingMe = true;
    core.m_targetRespondedToUs = true;
    core.m_selectionId = "logged-selection";
    core.m_selectionReason = "directed caller";
    core.m_selectionClass = "directed-caller";
    core.m_selectionScore = 99999;
    core.m_activeAttempt = 47;
    core.m_suspendedTarget.callsign = "B1STALE";
    core.m_suspendedTarget.bandIndex = 8;
    core.m_suspendedSelectionId = "stale-selection";
    core.m_targetRetryAfter.insert(core.targetScopeKey("A1DONE", 8, "FT8"),
                                   QDateTime::currentDateTimeUtc().addSecs(120));
    core.m_targetAttemptTimer.start();
    core.m_quietBandTimer.invalidate();
    core.m_currentDialFrequencyHz = 14074000;
    QStringList loggedQso;
    loggedQso << "20261005 150000" << "A1DONE" << "AA00"
              << "14074000" << "FT8";
    const int beforeLoggedStop = disableAutoRequests;
    core.onMSHVQsoLogged(loggedQso);
    assert(core.m_postQsoGuardTimer->isActive());
    assert(core.m_currentTarget.callsign == "A1DONE");
    assert(core.m_state == AutoDxerCore::WaitingForQSO);
    assert(disableAutoRequests == beforeLoggedStop);
    const int beforeGuardBandChanges = bandChanges;
    core.switchBand(true);
    assert(bandChanges == beforeGuardBandChanges);
    assert(core.m_currentTarget.callsign == "A1DONE");
    assert(core.m_postQsoGuardTimer->isActive());
    core.m_postQsoGuardTimer->stop();
    core.finishPostQsoGuard();
    assert(!core.m_currentTarget.isValid());
    assert(core.m_state == AutoDxerCore::Listening);
    assert(core.m_quietBandTimer.isValid());
    assert(disableAutoRequests == beforeLoggedStop + 1);
    assert(core.m_suspendedTarget.callsign.isEmpty());
    assert(!core.m_targetRetryAfter.contains(core.targetScopeKey("A1DONE", 8, "FT8")));
    assert(core.m_selectionId.isEmpty() && core.m_activeAttempt == 0);
    assert(emptyTargetChanges > 0);
    const QJsonObject completedStatus = core.autoDxStatus();
    assert(completedStatus.value("state").toString() == QStringLiteral("Listening"));
    assert(completedStatus.value("selection_id").toString().isEmpty());
    assert(completedStatus.value("target").toObject().value("call").toString().isEmpty());
    assert(tracker.applyWavelogAcknowledgedQso(
        QString(64, 'd'), "A1DONE", "AA00", 8, "FT8", "20261005"));

    // A later directed decode from the same callsign is permanently blocked
    // on the already-worked band/mode, even after the short recent-worked
    // cache expires. Different bands or modes remain separate slots.
    core.m_recentlyWorked.clear();
    core.m_workedTimestamps.clear();
    MultiAnswerModW postLogQueue(false);
    core.setQueueWidget(&postLogQueue);
    CachedDecode freshRepeat;
    freshRepeat.callsign = "A1DONE";
    freshRepeat.grid = "AA00";
    freshRepeat.dxccEntity = "Country A";
    freshRepeat.originalMessage = "OM0RX A1DONE -10";
    freshRepeat.bandIndex = 8;
    freshRepeat.audioFrequency = 1275;
    freshRepeat.dialFrequencyHz = 14074000;
    freshRepeat.snr = -10;
    freshRepeat.isLocalDecode = true;
    freshRepeat.timestamp = QDateTime::currentDateTimeUtc();
    core.m_decodeCache->addDecode("A1DONE", "AA00", "Country A",
                                  freshRepeat.originalMessage, 8, 1275,
                                  14074000, -10, false);
    core.considerCallingMePreemption(freshRepeat);
    assert(!core.m_currentTarget.isValid());
    assert(core.m_selectionId.isEmpty());
    assert(core.m_activeAttempt == 0);
    assert(core.m_suspendedTarget.callsign.isEmpty());
    core.setQueueWidget(nullptr);

    // An unrelated/manual log event must not terminate a genuine active QSO.
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "A1ONGOING";
    core.m_currentTarget.bandIndex = 8;
    core.m_currentTarget.isCallingMe = true;
    core.m_targetRespondedToUs = true;
    core.m_targetAttemptTimer.start();
    QStringList unrelatedQso;
    unrelatedQso << "20261005 150100" << "A1OTHER" << "AA01"
                 << "14074000" << "FT8";
    const int beforeUnrelatedLog = disableAutoRequests;
    core.onMSHVQsoLogged(unrelatedQso);
    assert(core.m_currentTarget.callsign == "A1ONGOING");
    assert(core.m_targetRespondedToUs);
    assert(disableAutoRequests == beforeUnrelatedLog);
    core.terminalClearCurrentTarget("fixture unrelated-log cleanup", false);

    // Engaged completion is a renewable lease from the latest valid reply,
    // not an absolute deadline from the first call. Fresh progress protects
    // the final 73/log sequence even after the original attempt budget.
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "A1HARD";
    core.m_currentTarget.bandIndex = 8;
    core.m_currentTarget.isCallingMe = true;
    core.m_targetRespondedToUs = true;
    core.m_selectionId = "hard-budget-selection";
    core.m_activeAttempt = 48;
    core.m_suspendedTarget.callsign = "B1STALE2";
    core.m_suspendedTarget.bandIndex = 8;
    core.m_normalCallSeconds = 0;
    core.m_engagedCompletionGraceSeconds = 60;
    core.m_targetAttemptElapsedOffsetMs = 60000;
    core.m_targetAttemptTimer.restart();
    core.m_lastTargetProgressUtc = QDateTime::currentDateTimeUtc();
    core.m_lastMissedCycleCheck = QDateTime();
    core.onDecodeComplete(false, 0);
    assert(core.m_currentTarget.callsign == "A1HARD");
    assert(core.m_targetRespondedToUs);

    // With no target progress for the full grace interval, stale ownership is
    // still terminal and receives the configured retry delay.
    core.m_lastTargetProgressUtc = QDateTime::currentDateTimeUtc().addSecs(-61);
    core.m_lastMissedCycleCheck = QDateTime();
    core.onDecodeComplete(false, 0);
    assert(!core.m_currentTarget.isValid());
    assert(core.m_suspendedTarget.callsign.isEmpty());
    assert(core.m_state == AutoDxerCore::Listening);
    assert(core.m_selectionId.isEmpty());
    assert(core.m_targetRetryAfter.contains(core.targetScopeKey("A1HARD", 8, "FT8")));
    core.m_normalCallSeconds = 120;
    core.m_targetAttemptElapsedOffsetMs = 0;

    // The final directed 73 after a logged QSO is protocol tail traffic, not
    // a fresh invitation. The recently-worked interval blocks reselection.
    const QString doneSlot = core.workedSlotKey("A1DONE", 8, "FT8");
    core.m_recentlyWorked.insert(doneSlot);
    core.m_workedTimestamps.insert(doneSlot, QDateTime::currentDateTime());
    MultiAnswerModW trailingQueue(false);
    core.setQueueWidget(&trailingQueue);
    core.m_enabled = true;
    core.m_state = AutoDxerCore::Listening;
    CachedDecode trailing73;
    trailing73.callsign = "A1DONE";
    trailing73.grid = "AA00";
    trailing73.dxccEntity = "Country A";
    trailing73.originalMessage = "OM0RX A1DONE 73";
    trailing73.bandIndex = 8;
    trailing73.audioFrequency = 1275;
    trailing73.dialFrequencyHz = 14074000;
    trailing73.snr = -10;
    trailing73.isLocalDecode = true;
    trailing73.timestamp = QDateTime::currentDateTimeUtc();
    core.considerCallingMePreemption(trailing73);
    assert(!core.m_currentTarget.isValid());
    core.setQueueWidget(nullptr);

    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "A1DONE";
    core.m_currentTarget.bandIndex = 8;
    core.m_currentTarget.isCallingMe = true;
    core.m_targetRespondedToUs = true;
    core.m_targetAttemptTimer.start();
    core.m_quietBandTimer.invalidate();
    core.onAutoModeChanged(false);
    assert(core.m_currentTarget.callsign == "A1DONE");
    assert(core.m_autoOffReconcileTimer->isActive());
    core.onAutoModeChanged(true);
    assert(!core.m_autoOffReconcileTimer->isActive());
    core.reconcileSustainedAutoOff();
    assert(core.m_currentTarget.callsign == "A1DONE");

    // A repeated/late false edge is correlated to the exact target that owned
    // the first edge and cannot clear a replacement target.
    core.onAutoModeChanged(false);
    assert(core.m_autoOffPendingCallsign == "A1DONE");
    core.m_currentTarget.callsign = "A1OTHER";
    core.onAutoModeChanged(false);
    assert(core.m_autoOffPendingCallsign == "A1DONE");
    core.reconcileSustainedAutoOff();
    assert(core.m_currentTarget.callsign == "A1OTHER");

    core.m_currentTarget.callsign = "A1DONE";
    core.onAutoModeChanged(true);
    const int beforeTerminalStop = disableAutoRequests;
    core.onAutoModeChanged(false);
    core.reconcileSustainedAutoOff();
    assert(!core.m_currentTarget.isValid());
    assert(core.m_state == AutoDxerCore::Listening);
    assert(core.m_quietBandTimer.isValid());
    assert(disableAutoRequests == beforeTerminalStop + 1);
    core.reconcileSustainedAutoOff();
    assert(disableAutoRequests == beforeTerminalStop + 1);

    core.m_enabled = true;
    core.setCurrentBand(8);
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "B1NORMAL";
    core.m_currentTarget.bandIndex = 8;
    core.m_currentTargetIsATNO = false;
    core.m_currentTargetIsNewSlot = false;
    core.m_targetRespondedToUs = false;
    core.m_normalCallSeconds = 0; // deterministic expiry; 120/240 boundaries above
    core.m_atnoMinimumCallSeconds = 0; // this fixture tests rotation, not ATNO persistence
    core.m_targetAttemptTimer.start();
    core.m_lastMissedCycleCheck = QDateTime();
    core.m_decodeCache->clear();
    const int beforeNormalRotation = disableAutoRequests;
    core.onDecodeComplete(false, 0);
    assert(!core.m_currentTarget.isValid());
    assert(core.m_state == AutoDxerCore::Listening);
    assert(disableAutoRequests == beforeNormalRotation + 1);

    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "B1DX";
    core.m_currentTarget.bandIndex = 8;
    core.m_currentTarget.priority = 10000;
    core.m_currentTargetIsATNO = true;
    core.m_currentTargetIsNewSlot = false;
    core.m_persistNewDxccWhileHeard = true;
    core.m_atnoChaseType = AutoDxerCore::ATNOChaseBoth;
    core.m_targetRespondedToUs = false;
    core.m_targetHeardFreshSeconds = 60;
    core.m_decodeCache->addDecode("B1DX", "BB00", "Country B",
                                  "CQ B1DX BB00", 8, 1100, 14074000, -5, true);
    core.m_targetAttemptTimer.start();
    core.m_lastMissedCycleCheck = QDateTime();
    core.onDecodeComplete(false, 0);
    assert(!core.m_currentTarget.isValid());
    assert(core.m_state == AutoDxerCore::Listening);
    assert(disableAutoRequests == beforeNormalRotation + 2);
    assert(core.targetLocallyFresh("B1DX", 8, 60));
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    core.evaluateTargets();
    assert(!core.m_waitingForSlotAnalysis);
    assert(!core.m_currentTarget.isValid());
    core.m_targetRetryAfter.clear();

    // A closed current band leaves immediately only from a genuinely idle state.
    core.m_enabled = true;
    core.m_bandSwitchingEnabled = true;
    core.m_state = AutoDxerCore::Listening;
    core.setCurrentBand(6);
    assert(!core.m_bandManager->isBandOpenNow(6));
    core.checkTimeout();
    assert(bandChanges == 1);
    assert(core.m_bandChangePending);
    assert(core.m_quietBandTimer.isValid());
    core.onBandChangeFailed(requestedBand, "fixture prepare rejection");
    assert(!core.m_bandChangePending);
    assert(core.m_quietBandTimer.isValid());
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "B1DX";
    core.m_currentTarget.bandIndex = 6;
    core.checkTimeout();
    assert(bandChanges == 1);
    core.m_state = AutoDxerCore::Listening;
    core.m_currentTarget.clear();
    armCrossBand(core, "B1DX");
    core.checkTimeout();
    assert(bandChanges == 1);
    core.clearPendingCrossBandVerification();
    core.m_waitingForSlotAnalysis = true;
    core.checkTimeout();
    assert(bandChanges == 1);
    core.m_pendingSlotAnalysisTarget.callsign = "B1DX";
    core.m_pendingSlotAnalysisTarget.bandIndex = 6;
    SlotAnalysis closedAnalysis = {};
    closedAnalysis.suggestedFreq = 1500;
    const int txBeforeClosedSlot = txFrequencyChanges;
    core.onSlotAnalysisReady(closedAnalysis);
    assert(!core.m_waitingForSlotAnalysis);
    assert(txFrequencyChanges == txBeforeClosedSlot);
    assert(bandChanges == 2);
    core.onBandChangeFailed(requestedBand, "fixture closed-slot rejection");

    // At quiet expiry, priority-zero traffic is still quiet and a candidate
    // rejected by the durable pending-history guard cannot postpone QSY.
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    core.setCurrentBand(8);
    // Band 6 is deliberately closed by the schedule fixture above; include
    // unrestricted band 9 so a quiet-band QSY has a deterministic destination.
    core.m_bandManager->setEnabledBands(QList<int>() << 6 << 8 << 9);
    core.m_quietBandSeconds = 0;
    // Two consecutive ordinary quiet-band attempts inside the 180-second
    // dwell remain blocked. Verification/origin-return paths are separate
    // explicit flows and are not modeled as ordinary quiet QSY here.
    core.m_selectionConfig.minimumBandDwellSeconds = 180;
    core.m_bandDwellTimer.restart();
    const int beforeDwellBlocked = bandChanges;
    core.switchBand();
    core.switchBand();
    assert(bandChanges == beforeDwellBlocked);
    // This block isolates quiet-expiry/priority behavior. Minimum-dwell
    // blocking and schedule overrides are covered by the selection-policy
    // fixture, so expire that independent gate deterministically here.
    core.m_selectionConfig.minimumBandDwellSeconds = 0;
    core.m_lastBandSwitchTime = QDateTime();
    core.m_quietBandTimer.start();
    core.m_decodeCache->clear();
    assert(tracker.applyWavelogAcknowledgedQso(
        QString(64, 'c'), "A1AAA", "AA00", 8, "FT8", "20261005"));
    core.m_decodeCache->addDecode("A1BBB", "AA00", "Country A",
                                  "CQ A1BBB AA00", 8, 1000, 14074000, -10, true);
    const int beforePriorityZero = bandChanges;
    core.checkTimeout();
    assert(bandChanges == beforePriorityZero + 1);
    core.onBandChangeFailed(requestedBand, "fixture priority-zero rejection");

    core.m_decodeCache->clear();
    core.m_decodeCache->addDecode("B1BBB", "BB00", "Country B",
                                  "CQ B1BBB BB00", 8, 1100, 14074000, -5, true);
    core.m_pendingWavelogCalls.insert("B1BBB");
    core.m_lastBandSwitchTime = QDateTime();
    const int beforeScoredRejected = bandChanges;
    core.checkTimeout();
    assert(bandChanges == beforeScoredRejected + 1);
    core.onBandChangeFailed(requestedBand, "fixture scored rejection");
    core.m_pendingWavelogCalls.clear();

    // A last-second eligible target accepted for slot analysis owns the band
    // and suppresses QSY; an active QSO does the same.
    core.m_decodeCache->clear();
    core.m_decodeCache->addDecode("B1BBB", "BB00", "Country B",
                                  "CQ B1BBB BB00", 8, 1100, 14074000, -5, true);
    core.m_slotFinder->clearData();
    core.m_lastBandSwitchTime = QDateTime();
    const int beforeAccepted = bandChanges;
    core.checkTimeout();
    assert(core.m_waitingForSlotAnalysis);
    assert(bandChanges == beforeAccepted);
    core.m_waitingForSlotAnalysis = false;
    core.m_pendingSlotAnalysisTarget = ScoredTarget();
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "B1BBB";
    core.m_currentTarget.bandIndex = 8;
    core.checkTimeout();
    assert(bandChanges == beforeAccepted);
    core.m_state = AutoDxerCore::Listening;
    core.m_currentTarget.clear();

    // Baseline patrol owns an independent deadline and round-robin cursor.
    // A verification excursion and its origin return do not restart or move
    // either one; the overdue patrol resumes at the next schedule-open band.
    core.m_bandManager->setEnabledBands(QList<int>() << 6 << 8 << 9 << 10);
    core.setCurrentBand(8);
    core.m_patrolCursorBand = 8;
    core.m_patrolTimer.invalidate();
    core.m_pendingCrossBandCallsign = "B1EXCURSE";
    core.m_pendingCrossBandBand = 10;
    core.m_pendingCrossBandReturnBand = 8;
    core.m_pendingCrossBandTime = QDateTime::currentDateTimeUtc();
    core.beginBandChange(10);
    quint64 excursionRequest = core.activeBandChangeRequestId();
    core.onBandChangeCompleteForRequest(10, excursionRequest);
    assert(core.m_currentBandIndex == 10);
    assert(core.m_patrolCursorBand == 8);
    assert(!core.m_patrolTimer.isValid());
    assert(core.returnFromPendingCrossBandVerification("fixture patrol excursion"));
    quint64 returnRequest = core.activeBandChangeRequestId();
    core.onBandChangeCompleteForRequest(8, returnRequest);
    assert(core.m_currentBandIndex == 8);
    assert(core.m_patrolCursorBand == 8);
    assert(!core.m_patrolTimer.isValid());

    core.m_selectionConfig.minimumBandDwellSeconds = 0;
    core.m_lastBandSwitchTime = QDateTime();
    core.m_patrolTimer.start();
    core.m_quietBandSeconds = 0;
    const int beforePatrol = bandChanges;
    core.switchBand();
    assert(bandChanges == beforePatrol + 1 && requestedBand == 9);
    quint64 patrolRequest = core.activeBandChangeRequestId();
    core.onBandChangeCompleteForRequest(9, patrolRequest);
    assert(core.m_patrolCursorBand == 9);
    core.m_lastBandSwitchTime = QDateTime();
    core.switchBand();
    assert(requestedBand == 10);
    patrolRequest = core.activeBandChangeRequestId();
    core.onBandChangeCompleteForRequest(10, patrolRequest);
    assert(core.m_patrolCursorBand == 10);
    core.m_lastBandSwitchTime = QDateTime();
    core.switchBand();
    assert(requestedBand == 8); // closed band 6 is skipped without starvation
    patrolRequest = core.activeBandChangeRequestId();
    core.onBandChangeCompleteForRequest(8, patrolRequest);
    assert(core.m_patrolCursorBand == 8);

    // A proven manual/external band change is different provenance: respect
    // operator intent by anchoring the cursor and granting a fresh interval.
    core.m_patrolTimer.invalidate();
    core.onBandChangedExternally(10);
    assert(core.m_currentBandIndex == 10);
    assert(core.m_patrolCursorBand == 10);
    assert(core.m_patrolTimer.isValid());
    core.onBandChangedExternally(8);
    assert(core.m_patrolCursorBand == 8);

    // Operator provenance is retained even while AutoDX is disabled.  A
    // later enable starts a fresh deadline at the observed band and rotates
    // from that anchor rather than an old cursor.
    core.setEnabled(false);
    assert(!core.m_enabled && !core.m_patrolTimer.isValid());
    core.onBandChangedExternally(10);
    assert(core.m_currentBandIndex == 10);
    assert(core.m_patrolCursorBand == 10);
    assert(!core.m_patrolTimer.isValid());
    core.setEnabled(true);
    assert(core.m_enabled && core.m_patrolTimer.isValid());
    core.m_quietBandSeconds = 0;
    core.m_selectionConfig.minimumBandDwellSeconds = 0;
    core.m_lastBandSwitchTime = QDateTime();
    const int beforeReenabledPatrol = bandChanges;
    core.switchBand();
    assert(bandChanges == beforeReenabledPatrol + 1);
    assert(requestedBand == 8); // closed 6 is skipped after the new anchor 10
    core.onBandChangeFailed(requestedBand, "fixture re-enabled patrol cleanup");

    // A final-proof failure after CAT has already confirmed destination keeps
    // TX inhibited but reconciles the planner to the radio's observed band.
    core.setCurrentBand(8);
    core.m_quietBandTimer.start();
    core.beginBandChange(9);
    const quint64 observedFailureRequest = core.activeBandChangeRequestId();
    core.onBandChangeFailedForRequest(
        9, "fixture final proof failure", observedFailureRequest, true);
    assert(!core.m_bandChangePending);
    assert(core.m_currentBandIndex == 9);
    assert(core.m_quietBandTimer.isValid());

    // A callback from an older same-band request cannot clear or complete the
    // newer request. Only the exact active request identity owns cleanup.
    core.setCurrentBand(8);
    core.beginBandChange(9);
    const quint64 staleRequest = core.activeBandChangeRequestId();
    core.onBandChangeFailedForRequest(9, "fixture first request failed", staleRequest, false);
    core.beginBandChange(9);
    const quint64 currentRequest = core.activeBandChangeRequestId();
    assert(currentRequest != staleRequest);
    core.onBandChangeFailedForRequest(9, "fixture late stale failure", staleRequest, false);
    core.onBandChangeCompleteForRequest(9, staleRequest);
    assert(core.m_bandChangePending);
    assert(core.m_requestedBandIndex == 9);
    assert(core.activeBandChangeRequestId() == currentRequest);
    assert(core.m_currentBandIndex == 8);
    core.onBandChangeFailedForRequest(9, "fixture current request failed", currentRequest, false);
    assert(!core.m_bandChangePending);

    // A destination window that closes while CAT QSY is in flight returns to
    // origin before any dial/TX-frequency action.
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    core.setCurrentBand(8);
    core.m_pendingCrossBandCallsign = "B1DX";
    core.m_pendingCrossBandBand = 6;
    core.m_pendingCrossBandReturnBand = 8;
    core.m_pendingCrossBandDialFreq = 7074000;
    core.beginBandChange(6);
    const quint64 closedDestinationRequest = core.activeBandChangeRequestId();
    const int beforeClosedDestination = bandChanges;
    core.onBandChangeCompleteForRequest(6, closedDestinationRequest);
    assert(bandChanges == beforeClosedDestination + 1);
    assert(requestedBand == 8);
    assert(dialChanges == 0 && txFrequencyChanges == 0);

    // Authority loss cancels an unengaged cross-band verification and returns
    // to the saved origin instead of leaving the radio parked at destination.
    core.m_desiredEnabled = true;
    core.m_enabled = true;
    core.m_state = AutoDxerCore::Listening;
    core.setCurrentBand(11);
    armCrossBand(core, "KP5AA");
    const int beforeAuthorityReturn = bandChanges;
    core.revokeHistoricalNovelty("unavailable");
    assert(core.m_enabled);
    assert(core.m_desiredEnabled);
    assert(!core.m_historicalNoveltyAllowed);
    assert(core.m_pendingCrossBandCallsign.isEmpty());
    assert(bandChanges == beforeAuthorityReturn + 1 && requestedBand == 6);

    // If the outbound QSY is still in flight, preserve origin/destination until
    // completion, then return without emitting dial or TX-frequency actions.
    core.setCurrentBand(6);
    armCrossBand(core, "KP5AA");
    core.beginBandChange(11);
    const quint64 inflightRequest = core.activeBandChangeRequestId();
    core.revokeHistoricalNovelty("blocked-diverged");
    assert(core.m_pendingCrossBandReturnBand == 6);
    const int beforeInflightCompletion = bandChanges;
    core.onBandChangeCompleteForRequest(11, inflightRequest);
    assert(bandChanges == beforeInflightCompletion + 1 && requestedBand == 6);
    assert(dialChanges == 0);
    assert(txFrequencyChanges == 0);

    // A pending Wavelog identity never removes an engaged/responded native QSO.
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "KP5AA";
    core.m_currentTarget.bandIndex = 6;
    core.m_targetRespondedToUs = true;
    core.m_pendingWavelogCalls.insert("KP5AA");
    core.cancelPendingWavelogPaths();
    assert(core.m_currentTarget.callsign == "KP5AA");
    assert(core.m_targetRespondedToUs);
    core.m_pendingWavelogCalls.clear();
    core.m_currentTarget.clear();
    core.m_targetRespondedToUs = false;

    // One transport timeout fails closed for new historical novelty while
    // preserving only the exact in-progress cross-band verification. A
    // successful retry clears the bounded transport state. Sustained loss
    // terminally returns and dequeues the verification.
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    core.m_state = AutoDxerCore::Listening;
    core.setCurrentBand(11);
    core.m_quietBandSeconds = 300;
    core.m_bandSwitchCooldownSeconds = 120;
    armCrossBand(core, "B1TRANS");
    const int beforeTransient = bandChanges;
    core.noteTransientHistoryFailure("fixture-timeout");
    assert(!core.m_historicalNoveltyAllowed);
    assert(core.m_historyTransientFailureCount == 1);
    assert(core.m_pendingCrossBandCallsign == "B1TRANS");
    assert(core.pendingCrossBandHistoryAllowed("B1TRANS"));
    assert(!core.pendingCrossBandHistoryAllowed("B1OTHER"));
    assert(bandChanges == beforeTransient);
    assert(core.m_historyTransientGraceTimer->isActive());
    assert(core.m_historyTransientGraceTimer->remainingTime() > 0);
    assert(core.m_historyTransientGraceTimer->remainingTime() <= 20000);
    assert(core.m_historyRetryNotBefore > QDateTime::currentDateTimeUtc());
    core.clearTransientHistoryFailure();
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    assert(core.m_historyTransientFailureCount == 0);
    assert(!core.m_historyTransientGraceTimer->isActive());
    assert(core.m_pendingCrossBandCallsign == "B1TRANS");

    core.noteTransientHistoryFailure("fixture-timeout");
    const QDateTime firstRetry = core.m_historyRetryNotBefore;
    core.noteTransientHistoryFailure("fixture-timeout");
    assert(core.m_historyRetryNotBefore > firstRetry);
    const int beforeTerminalTransient = bandChanges;
    core.noteTransientHistoryFailure("fixture-timeout");
    assert(core.m_pendingCrossBandCallsign.isEmpty());
    assert(bandChanges == beforeTerminalTransient + 1 && requestedBand == 6);
    assert(core.crossBandRetryDeferred("B1TRANS", 11,
                                      QDateTime::currentDateTimeUtc()));
    assert(core.m_crossBandRetryAfter.value(core.crossBandRetryKey("B1TRANS", 11))
               > QDateTime::currentDateTimeUtc().addSecs(300));
    core.onBandChangeFailed(requestedBand, "fixture terminal-return cleanup");
    core.clearTransientHistoryFailure();

    // The absolute 20-second wall-clock deadline terminalizes without a
    // second or third reply callback. This is the delayed-event-loop path:
    // the callback observes an already-aged first failure and cannot extend it.
    core.setCurrentBand(11);
    core.m_state = AutoDxerCore::Listening;
    armCrossBand(core, "B1DEAD");
    core.m_historyRequestGeneration = 41;
    core.noteTransientHistoryFailure("fixture-single-timeout");
    core.m_historyFirstTransientFailureAt = QDateTime::currentDateTimeUtc().addSecs(-21);
    const int beforeAbsoluteDeadline = bandChanges;
    core.expireTransientHistoryGrace();
    assert(core.m_pendingCrossBandCallsign.isEmpty());
    assert(bandChanges == beforeAbsoluteDeadline + 1 && requestedBand == 6);
    assert(core.historyReplyIsStale(41));
    assert(!core.historyReplyIsStale(42));
    assert(core.m_historyTransientTerminalized);
    core.m_historyRequestGeneration = 42;
    const quint64 terminalWatermark = core.m_historyIgnoreRepliesThroughGeneration;
    core.expireTransientHistoryGrace();
    core.evaluateTargets();
    assert(core.m_historyIgnoreRepliesThroughGeneration == terminalWatermark);
    assert(!core.historyReplyIsStale(42));
    core.onBandChangeFailed(requestedBand, "fixture absolute-deadline cleanup");
    // A fresh successful N+1 response clears only the transport episode and
    // may authorize future work; it never revives the terminalized action.
    core.clearTransientHistoryFailure();
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    assert(!core.m_historyTransientTerminalized);

    // If the absolute deadline fires while CAT is still outbound, a late
    // reply cannot revive that action. A later fresh generation may recover
    // authority for future work, but completion still returns this expired
    // verification to its saved origin.
    core.setCurrentBand(6);
    core.m_state = AutoDxerCore::Listening;
    armCrossBand(core, "B1LATE");
    core.beginBandChange(11);
    const quint64 lateBandRequest = core.activeBandChangeRequestId();
    core.m_historyRequestGeneration = 50;
    core.noteTransientHistoryFailure("fixture-late-reply");
    core.m_historyFirstTransientFailureAt = QDateTime::currentDateTimeUtc().addSecs(-21);
    core.expireTransientHistoryGrace();
    assert(core.m_pendingCrossBandCallsign == "B1LATE");
    assert(!core.m_pendingCrossBandTerminalReason.isEmpty());
    assert(core.historyReplyIsStale(50));
    assert(!core.historyReplyIsStale(51));
    core.clearTransientHistoryFailure();
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    const int beforeLateCompletion = bandChanges;
    core.onBandChangeCompleteForRequest(11, lateBandRequest);
    assert(bandChanges == beforeLateCompletion + 1 && requestedBand == 6);
    assert(core.m_pendingCrossBandCallsign.isEmpty());
    core.onBandChangeFailed(requestedBand, "fixture late-reply return cleanup");

    // A pre-CAT failure after terminal history expiry is already at origin:
    // dequeue/back off exactly once and never emit a redundant return QSY.
    core.setCurrentBand(6);
    core.m_state = AutoDxerCore::Listening;
    armCrossBand(core, "B1PREFAIL");
    core.beginBandChange(11);
    const quint64 terminalPreCatRequest = core.activeBandChangeRequestId();
    core.m_pendingCrossBandTerminalReason = "fixture terminal pre-CAT";
    const int beforeTerminalPreCatFailure = bandChanges;
    core.onBandChangeFailedForRequest(
        11, "fixture pre-CAT failure", terminalPreCatRequest, false);
    assert(bandChanges == beforeTerminalPreCatFailure);
    assert(core.m_currentBandIndex == 6);
    assert(core.m_pendingCrossBandCallsign.isEmpty());
    assert(core.crossBandRetryDeferred("B1PREFAIL", 11,
                                      QDateTime::currentDateTimeUtc()));
    assert(core.m_quietBandTimer.isValid());

    // A failure reported after CAT observed the destination must reconcile to
    // that band, then return once to the saved origin before clearing state.
    core.setCurrentBand(6);
    core.m_state = AutoDxerCore::Listening;
    armCrossBand(core, "B1POSTFAIL");
    core.beginBandChange(11);
    const quint64 terminalPostCatRequest = core.activeBandChangeRequestId();
    core.m_pendingCrossBandTerminalReason = "fixture terminal post-CAT";
    const int beforeTerminalPostCatFailure = bandChanges;
    core.onBandChangeFailedForRequest(
        11, "fixture post-CAT failure", terminalPostCatRequest, true);
    assert(bandChanges == beforeTerminalPostCatFailure + 1);
    assert(core.m_currentBandIndex == 11);
    assert(requestedBand == 6);
    assert(core.m_pendingCrossBandCallsign.isEmpty());
    core.onBandChangeFailed(requestedBand, "fixture post-CAT return cleanup");

    // A terminal verification cannot win again at the shorter switch
    // cooldown; ordinary quiet-band rotation remains able to progress.
    core.setCurrentBand(8);
    core.m_state = AutoDxerCore::Listening;
    core.m_enabled = true;
    core.m_bandSwitchingEnabled = true;
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    core.m_bandManager->setEnabledBands(QList<int>() << 6 << 8 << 9);
    core.m_quietBandSeconds = 0;
    core.m_bandSwitchCooldownSeconds = 0;
    core.m_selectionConfig.minimumBandDwellSeconds = 0;
    core.m_lastBandSwitchTime = QDateTime();
    core.m_quietBandTimer.start();
    core.m_decodeCache->clear();
    const int beforeQuietProgress = bandChanges;
    core.checkTimeout();
    assert(bandChanges == beforeQuietProgress + 1);
    core.onBandChangeFailed(requestedBand, "fixture quiet progress cleanup");

    // Wavelog-acknowledged tracker state is authoritative for novelty scoring.
    assert(tracker.applyWavelogAcknowledgedQso(
        QString(64, 'a'), "A1AAA", "", 6, "FT8", "20261005"));
    core.setCurrentBand(6);
    CachedDecode worked;
    worked.callsign = "A1BBB";
    worked.dxccEntity = "Country A";
    worked.originalMessage = "CQ A1BBB AA00";
    worked.bandIndex = 6;
    worked.audioFrequency = 1000;
    worked.dialFrequencyHz = 7074000;
    worked.snr = -10;
    worked.isCQ = true;
    worked.isLocalDecode = true;
    assert(core.m_targetScorer->scoreTarget(worked).priority == 0);

    CachedDecode needed = worked;
    needed.callsign = "B1BBB";
    needed.dxccEntity = "Country B";
    needed.originalMessage = "CQ B1BBB BB00";
    core.m_targetScorer->setHistoricalNoveltyAllowed(false);
    assert(core.m_targetScorer->scoreTarget(needed).priority == 0);
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    const ScoredTarget neededTarget = core.m_targetScorer->scoreTarget(needed);
    assert(neededTarget.priority > 0);
    assert(neededTarget.isNewDXCC);
    assert(!neededTarget.isOrdinaryNewCallFallback);

    // An overdue baseline patrol outranks a lower-class same-band
    // off-standard new-slot alert.  The evidence remains cached: urgent
    // all-time-new DXCC may interrupt, and the slot is reconsidered after the
    // patrol deadline is no longer due.
    core.m_spotAggregator->clearSpots();
    core.setCurrentBand(9);
    core.m_currentDialFrequencyHz = core.m_bandManager->bandFrequencyHz(9);
    core.m_enabled = true;
    core.m_state = AutoDxerCore::Listening;
    core.m_historicalNoveltyAllowed = true;
    core.m_targetScorer->setHistoricalNoveltyAllowed(true);
    core.m_pendingNonStdCallsign.clear();
    core.m_lastNonStdQsyTime = QDateTime();
    assert(!core.m_dxccTracker->isNewDXCCByCall("A1SLOT"));
    assert(core.m_dxccTracker->isNewBandSlotByCall("A1SLOT", 9));
    addCrossBandAlert(core, "A1SLOT", 9, 10000);
    core.m_quietBandSeconds = 0;
    core.m_patrolTimer.start();
    const int beforePatrolOwnedDial = dialChanges;
    core.checkSameBandNonStdFreqAlerts();
    assert(dialChanges == beforePatrolOwnedDial);
    assert(core.m_pendingNonStdCallsign.isEmpty());

    core.m_spotAggregator->clearSpots();
    assert(core.m_dxccTracker->isNewDXCCByCall("B1URGENT"));
    addCrossBandAlert(core, "B1URGENT", 9, 12000);
    core.checkSameBandNonStdFreqAlerts();
    assert(dialChanges == beforePatrolOwnedDial + 1);
    assert(core.m_pendingNonStdCallsign == "B1URGENT");
    core.m_pendingNonStdCallsign.clear();
    core.m_pendingNonStdDialFreq = 0;
    core.m_pendingNonStdTime = QDateTime();
    core.m_lastNonStdQsyTime = QDateTime();

    core.m_spotAggregator->clearSpots();
    addCrossBandAlert(core, "A1SLOT", 9, 10000);
    core.m_quietBandSeconds = 300;
    core.m_patrolTimer.restart();
    const int beforeLaterSlotDial = dialChanges;
    core.checkSameBandNonStdFreqAlerts();
    assert(dialChanges == beforeLaterSlotDial + 1);
    assert(core.m_pendingNonStdCallsign == "A1SLOT");
    core.m_pendingNonStdCallsign.clear();
    core.m_pendingNonStdDialFreq = 0;
    core.m_pendingNonStdTime = QDateTime();
    core.m_lastNonStdQsyTime = QDateTime();
    core.m_spotAggregator->clearSpots();

    // Normal Auto DX remains responsive to an ordinary eligible CQ on its
    // current band. Only Full Hunting requires a complete all-band priority
    // patrol first. A currently eligible cluster/DXpedition row blocks the
    // fallback in either mode.
    core.m_bandManager->setEnabledBands(QList<int>() << 6 << 8 << 9);
    const QSet<int> openPriorityBands = core.openPatrolBands();
    assert(!openPriorityBands.isEmpty());
    core.m_fullHuntingEnabled = false;
    core.resetPriorityPatrolCycle();
    assert(!core.priorityPatrolComplete());
    assert(core.ordinaryNewCallFallbackAllowed());
    core.m_fullHuntingEnabled = true;
    assert(!core.ordinaryNewCallFallbackAllowed());
    for (int band : openPriorityBands) {
        core.markPriorityPatrolBandChecked(band);
    }
    assert(core.priorityPatrolComplete());
    assert(core.ordinaryNewCallFallbackAllowed());
    QJsonObject dxpeditionOpportunity;
    dxpeditionOpportunity["call"] = "B1DXPED";
    dxpeditionOpportunity["dxpedition"] = true;
    core.m_clusterChaseQueue.append(dxpeditionOpportunity);
    assert(core.hasEligiblePriorityOpportunity());
    assert(!core.ordinaryNewCallFallbackAllowed());
    core.m_clusterChaseQueue = QJsonArray();
    assert(core.ordinaryNewCallFallbackAllowed());
    const int reopenedBand = *openPriorityBands.constBegin();
    core.m_priorityPatrolOpenBands.remove(reopenedBand);
    assert(!core.priorityPatrolComplete());
    core.refreshPriorityPatrolSchedule();
    assert(core.m_priorityPatrolCheckedBands.isEmpty());
    assert(!core.ordinaryNewCallFallbackAllowed());
    core.resetPriorityPatrolCycle();
    assert(!core.priorityPatrolComplete());
    core.m_fullHuntingEnabled = false;
    assert(core.ordinaryNewCallFallbackAllowed());

    // An unverified cross-band prospect returns to the saved origin instead
    // of leaving the radio parked on the destination's standard frequency.
    core.m_enabled = true;
    core.m_state = AutoDxerCore::Listening;
    core.m_currentTarget.clear();
    core.m_targetRespondedToUs = false;
    core.setCurrentBand(11);
    armCrossBand(core, "B1DX");
    core.m_pendingCrossBandTime = QDateTime::currentDateTimeUtc().addSecs(-61);
    const int beforeVerifyTimeout = bandChanges;
    core.evaluateTargets();
    assert(bandChanges == beforeVerifyTimeout + 1);
    assert(requestedBand == 6);
    assert(core.m_pendingCrossBandCallsign.isEmpty());
    assert(core.m_pendingCrossBandBand == -1);
    assert(core.m_pendingCrossBandReturnBand == -1);
    assert(core.m_lastBandSwitchTime.isValid());

    // The right-click Ignore path uses the row's resolved callsign directly.
    // Ignoring the active target must persist the exact band/mode exclusion,
    // request an immediate native TX halt/reset, and release target ownership.
    int immediateIgnoreStops = 0;
    QObject::connect(&core, &AutoDxerCore::requestImmediateStopAndReset,
                     [&]() { ++immediateIgnoreStops; });
    core.setCurrentMode("FT8");
    core.setCurrentBand(8);
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "B1IGNORE";
    core.m_currentTarget.bandIndex = 8;
    core.m_currentTargetIsDxpedition = false;
    core.ignoreStation("B1IGNORE");
    assert(immediateIgnoreStops == 1);
    assert(!core.m_currentTarget.isValid());
    assert(core.isStationIgnored("B1IGNORE", 8, "FT8"));
    assert(QFile::exists(settings.path() + "/settings/database/autodx_ignore.json"));

    // Right-click Call next is a FIFO operator request, not a preemption. It
    // stays visible while another target owns the exchange, blocks patrol QSY,
    // and is removed only after native queue admission succeeds.
    MultiAnswerModW callerQueue(false);
    core.setQueueWidget(&callerQueue);
    core.m_slotFinder->clearData();
    // The preceding return-to-origin fixture intentionally leaves a simulated
    // CAT handoff outstanding.  A real decoded row cannot be queued during
    // that handoff, so finish the synthetic transition before exercising the
    // operator callers list.
    core.m_bandChangePending = false;
    core.m_pendingCrossBandTerminalReason.clear();
    core.m_state = AutoDxerCore::WaitingForQSO;
    core.m_currentTarget.callsign = "B1ACTIVE";
    core.m_currentTarget.bandIndex = 8;
    QStringList nextDecode;
    nextDecode << "120000" << "-7" << "0.1" << "1450"
               << "CQ B1NEXT BB00" << "Country B" << "1000"
               << "" << "" << "" << "" << "" << "1450";
    core.queueOperatorTarget(nextDecode);
    assert(core.m_currentTarget.callsign == "B1ACTIVE");
    assert(core.queuedOperatorCalls().size() == 1);
    const int beforeCallerQsy = bandChanges;
    core.switchBand(true);
    assert(bandChanges == beforeCallerQsy);

    core.m_currentTarget.clear();
    core.m_state = AutoDxerCore::Listening;
    core.evaluateTargets();
    assert(core.m_waitingForSlotAnalysis);
    assert(core.m_pendingSlotAnalysisTarget.callsign == "B1NEXT");
    assert(core.queuedOperatorCalls().size() == 1);
    SlotAnalysis callerAnalysis = {};
    callerAnalysis.suggestedFreq = 1750;
    callerAnalysis.alternateFreq = 1850;
    callerAnalysis.confidence = 1.0;
    callerAnalysis.reason = "operator-callers-test";
    core.onSlotAnalysisReady(callerAnalysis);
    assert(core.m_currentTarget.callsign == "B1NEXT");
    assert(core.queuedOperatorCalls().isEmpty());
    assert(callerQueue.setOperatorTxStage("B1NEXT", 2));
    const int manualStageRow = callerQueue.getNowList()->FindCallOrBaseCallRow("B1NEXT");
    assert(manualStageRow >= 0);
    assert(callerQueue.getNowList()->model.item(manualStageRow, 7)->text() == "2");

    QStringList removableDecode = nextDecode;
    removableDecode[4] = "CQ B1RMV BB00";
    core.queueOperatorTarget(removableDecode);
    const QJsonArray callers = core.queuedOperatorCalls();
    assert(callers.size() == 1);
    core.removeOperatorCall(callers.first().toObject().value("key").toString());
    assert(core.queuedOperatorCalls().isEmpty());
    core.setQueueWidget(nullptr);

    return 0;
}
