#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QSettings>
#include <QTemporaryDir>
#include <cassert>
#include <iostream>

#include "HvAutoDxer/autodxruntimeconfig.h"
#include "HvAutoDxer/bandmanager.h"

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    QTemporaryDir temp;
    assert(temp.isValid());
    QDir().mkpath(temp.path());
    QSettings s(temp.path() + "/autodx.ini", QSettings::IniFormat);
    s.setValue("AutoDx/Enabled", true);
    s.setValue("AutoDx/Modes", "FT8,FT4");
    s.setValue("AutoDx/ATNOChaseType", 2);
    s.setValue("AutoDx/ScarceThreshold", 7);
    s.setValue("BandSwitching/Enabled", true);
    s.setValue("FullHunting/Enabled", true);
    s.setValue("FullHunting/VisitSeconds", 165);
    s.setValue("AutomationTiming/NormalCallSeconds", 120);
    s.setValue("AutomationTiming/QuietBandSeconds", 305);
    s.setValue("AutomationTiming/QuietBandEmptyPeriods", 6);
    s.setValue("AutomationTiming/TargetHeardFreshSeconds", 65);
    s.setValue("AutomationTiming/CrossBandVerifySeconds", 70);
    s.setValue("AutomationTiming/BandSwitchCooldownSeconds", 130);
    s.setValue("AutomationTiming/PersistNewDxccWhileHeard", false);
    s.setValue("AutomationTiming/PersistNewBandSlotWhileHeard", true);
    s.setValue("TargetPriority/NewDxcc", 9001);
    s.setValue("TargetPriority/NewBandSlot", 901);
    s.setValue("TargetPriority/NewGrid", 501);
    s.setValue("TargetPriority/CallingMe", 401);
    s.setValue("TargetPriority/Cq", 201);
    s.setValue("TargetPriority/SnrPerDb", 11);
    s.setValue("TargetPriority/PreferNonEurope", true);
    s.setValue("TargetPriority/NonEuropeBoost", 5500);
    s.setValue("TargetPriority/DxpeditionBoost", 12000);
    s.setValue("Dxpedition/Enabled", true);
    s.setValue("Dxpedition/AllowSameBandOffStandardQsy", false);
    s.setValue("Dxpedition/AllowCrossBandQsy", true);
    s.setValue("Dxpedition/ChaseScope", "any-active");
    s.setValue("Dxpedition/MinSpotters", 3);
    s.setValue("Dxpedition/MaxSpotAgeSeconds", 240);
    s.setValue("Dxpedition/TxOffsetHz", 850);
    s.setValue("Dxpedition/ReturnToStandard", false);
    s.setValue("Eligibility/FilterMatrixEnabled", true);
    s.setValue("Eligibility/FilterNewCall", true);
    s.setValue("Eligibility/FilterNewDxcc", true);
    s.setValue("Eligibility/FilterNewContinent", true);
    s.setValue("Eligibility/FilterNewGrid", true);
    s.setValue("Eligibility/FilterNewCqZone", true);
    s.setValue("Eligibility/FilterNewItuZone", true);
    s.setValue("Eligibility/FilterBandCall", true);
    s.setValue("Eligibility/FilterBandDxcc", true);
    s.setValue("Eligibility/FilterBandContinent", true);
    s.setValue("Eligibility/FilterBandGrid", true);
    s.setValue("Eligibility/FilterBandCqZone", true);
    s.setValue("Eligibility/FilterBandItuZone", true);
    s.setValue("Eligibility/FilterContinents", "AF,AS,NA,OC,SA");
    s.setValue("Eligibility/AllowBandDxccOutsideContinent", false);
    s.setValue("Eligibility/FilterLotwOnly", true);
    s.setValue("Eligibility/MinSignal", -16);
    s.setValue("Eligibility/Treat73AsCq", true);
    s.setValue("Eligibility/WatchUnconfirmedDxcc", false);
    s.setValue("Eligibility/ExcludedCountriesByBand",
               "ALL: Japan\n30m: USA; Canada\n20m: Germany\ninvalid: France");
    s.setValue("Selection/Order", "last");
    s.setValue("Attempt/CallWindowSeconds", 240);
    s.setValue("Attempt/MaxConsecutiveWindows", 3);
    s.setValue("Attempt/SameTargetRetrySeconds", 75);
    s.setValue("Attempt/RecentQsoCooldownSeconds", 4321);
    s.setValue("Attempt/EngagedCompletionGraceSeconds", 61);
    s.setValue("Attempt/ATNOMinimumCallMinutes", 45);
    s.setValue("BandSwitching/MinimumDwellSeconds", 210);
    s.setValue("GridChase/Enabled", true);
    s.setValue("GridChase/USOnly", false);
    s.setValue("SpotSources/MinSNR", -17);
    s.setValue("SpotSources/Callsign", "om0rx");
    s.setValue("SpotSources/Grid", "jn88");
    s.setValue("SpotSources/RbnEnabled", false);
    s.setValue("SpotSources/RbnHost", "rbn.example.test");
    s.setValue("SpotSources/RbnPort", 7100);
    s.setValue("SpotSources/PskEnabled", true);
    s.setValue("SpotSources/PskPollInterval", 180);
    s.setValue("SpotSources/DxcEnabled", true);
    s.setValue("SpotSources/UsOnlyFilter", false);
    s.setValue("SpotSources/UseDefaultDxClusterServers", false);
    s.setValue("DxClusterServers/Count", 1);
    s.setValue("DxClusterServers/Server0", "Test|cluster.example.test|7300|true");
    s.setValue("AwardHunting/Enabled", true);
    s.setValue("AwardHunting/StackScores", true);
    s.setValue("AwardHunting/NewContinentWeight", 2600);
    s.setValue("ReferenceHunting/PotaEnabled", true);
    s.setValue("ReferenceHunting/SotaEnabled", false);
    s.setValue("ReferenceHunting/WwffEnabled", true);
    s.setValue("ReferenceHunting/PotaWeight", 1900);
    s.setValue("ReferenceHunting/NewReferenceWeight", 2600);
    s.setValue("PropagationAdaptation/WindowSeconds", 600);
    s.setValue("PileupStrategy/AudioOffsetsHz", "0,-100,100");
    s.setValue("PileupStrategy/RotateAfterAttempts", 3);
    s.setValue("DirectedCallers/InboxSize", 12);
    s.setValue("Campaign/Profile", "dxcc-challenge");
    s.setValue("Campaign/ReferenceWeightPercent", 125);
    s.setValue("OutcomeLearning/TelemetryFile", "logs/test-outcomes.jsonl");
    s.sync();

    const AutoDxRuntimeConfig c = AutoDxRuntimeConfig::load(temp.path());
    assert(c.desiredEnabled);
    assert(c.modes == (QStringList() << "FT8" << "FT4"));
    assert(c.modeAllowed("ft8"));
    assert(c.modeAllowed("FT4"));
    assert(c.effectiveEnabled("FT8"));
    assert(c.effectiveEnabled("FT4"));
    assert(AutoDxRuntimeConfig::acceptsExternalMode("FT8"));
    assert(AutoDxRuntimeConfig::acceptsExternalMode(" ft8 "));
    assert(AutoDxRuntimeConfig::acceptsExternalMode("FT4"));
    assert(!AutoDxRuntimeConfig::acceptsExternalMode(""));
    assert(!AutoDxRuntimeConfig::acceptsExternalMode("DIGU"));
    assert(AutoDxRuntimeConfig::explicitDigitalMode("FT8 -12 dB") == "FT8");
    assert(AutoDxRuntimeConfig::explicitDigitalMode("FT4 -7 dB") == "FT4");
    assert(AutoDxRuntimeConfig::explicitDigitalMode("DXpedition 14090.0").isEmpty());
    assert(!AutoDxRuntimeConfig::acceptsExternalMode(
        AutoDxRuntimeConfig::explicitDigitalMode("DXpedition 14090.0")));
    assert(c.bandSwitchingEnabled && c.atnoChaseType == 2 && c.scarceThreshold == 7);
    assert(c.fullHuntingEnabled && c.fullHuntingVisitSeconds == 165);
    assert(c.normalCallSeconds == 120 && c.quietBandSeconds == 305);
    assert(c.quietBandEmptyPeriods == 6);
    assert(c.targetHeardFreshSeconds == 65 && c.crossBandVerifySeconds == 70);
    assert(c.bandSwitchCooldownSeconds == 130);
    assert(c.atnoMinimumCallSeconds == 2700);
    assert(!c.persistNewDxccWhileHeard && c.persistNewBandSlotWhileHeard);
    assert(c.newDxccWeight == 9001 && c.newBandSlotWeight == 901 && c.newGridWeight == 501);
    assert(c.callingMeWeight == 401 && c.cqWeight == 201 && c.snrWeight == 11);
    assert(c.selection.filterMatrixEnabled && c.selection.filterNewCall);
    assert(c.selection.filterNewDxcc && c.selection.filterNewContinent);
    assert(c.selection.filterNewGrid && c.selection.filterNewCqZone && c.selection.filterNewItuZone);
    assert(c.selection.filterBandCall && c.selection.filterBandDxcc);
    assert(c.selection.filterBandContinent && c.selection.filterBandGrid);
    assert(c.selection.filterBandCqZone && c.selection.filterBandItuZone);
    assert(!c.selection.enabledContinents.contains("EU") && c.selection.enabledContinents.contains("AS"));
    assert(!c.selection.allowBandDxccOutsideContinent);
    assert(c.selection.lotwOnly && c.selection.minSignal == -16);
    assert(c.selection.preferNonEurope && c.selection.nonEuropeBoost == 5500);
    assert(c.dxpeditionBoost == 12000 && c.selection.selectionOrder == "last");
    assert(c.dxpeditionChaseEnabled && !c.dxpeditionAllowSameBandOffStandardQsy);
    assert(c.dxpeditionAllowCrossBandQsy && c.dxpeditionChaseAnyActive);
    assert(c.dxpeditionMinSpotters == 3 && c.dxpeditionMaxSpotAgeSeconds == 240);
    assert(c.dxpeditionTxOffsetHz == 850 && !c.dxpeditionReturnToStandard);
    assert(c.selection.treat73AsCq && !c.selection.watchUnconfirmedDxcc);
    assert(c.excludedCountriesByBand.value(-1).contains("JAPAN"));
    assert(c.excludedCountriesByBand.value(7).contains("UNITEDSTATES"));
    assert(c.excludedCountriesByBand.value(7).contains("CANADA"));
    assert(c.excludedCountriesByBand.value(8).contains("GERMANY"));
    assert(!c.excludedCountriesByBand.contains(-2));
    assert(c.selection.callWindowSeconds == 240 && c.selection.maxConsecutiveWindows == 3);
    assert(c.selection.sameTargetRetrySeconds == 75);
    assert(c.selection.recentQsoCooldownSeconds == 4321);
    assert(c.selection.minimumBandDwellSeconds == 210);
    assert(c.engagedCompletionGraceSeconds == 75);
    assert(c.gridChaseEnabled && !c.gridUsOnly && c.minSnr == -17);
    assert(c.callsign == "OM0RX" && c.grid == "JN88");
    assert(!c.rbnEnabled && c.rbnHost == "rbn.example.test" && c.rbnPort == 7100);
    assert(c.pskrEnabled && c.pskrPollInterval == 180);
    assert(c.dxClusterEnabled && !c.usOnly && !c.useDefaultServers);
    assert(c.customServers == (QStringList() << "Test|cluster.example.test|7300|true"));
    assert(c.awardHunting.enabled && c.awardHunting.stackScores);
    assert(c.awardHunting.newContinentWeight == 2600);
    assert(c.awardHunting.potaEnabled && !c.awardHunting.sotaEnabled
           && c.awardHunting.wwffEnabled);
    assert(c.awardHunting.potaWeight == 1900
           && c.awardHunting.newReferenceWeight == 2600);
    assert(c.propagationAdaptation.windowSeconds == 600);
    assert(c.pileupStrategy.audioOffsetsHz == (QList<int>() << 0 << -100 << 100));
    assert(c.pileupStrategy.rotateAfterAttempts == 3);
    assert(c.directedCallerInboxSize == 12);
    assert(c.campaignProfile == "dxcc-challenge");
    assert(c.awardHunting.dxccWeightPercent == 175);
    assert(c.awardHunting.stateWeightPercent == 75);
    assert(c.awardHunting.zoneWeightPercent == 100);
    assert(c.awardHunting.gridWeightPercent == 75);
    assert(c.awardHunting.referenceWeightPercent == 75);
    assert(c.outcomeTelemetryFile == "logs/test-outcomes.jsonl");

    s.setValue("Campaign/Profile", "custom");
    s.sync();
    const AutoDxRuntimeConfig customCampaign = AutoDxRuntimeConfig::load(temp.path());
    assert(customCampaign.awardHunting.referenceWeightPercent == 125);

    // Operator-configurable call ownership supports a longer four-minute
    // attempt without changing the state-machine contract.
    s.setValue("AutomationTiming/NormalCallSeconds", 240);
    s.sync();
    const AutoDxRuntimeConfig extendedCall = AutoDxRuntimeConfig::load(temp.path());
    assert(extendedCall.normalCallSeconds == 240);

    s.setValue("AutoDx/Modes", QStringList() << "FT8" << " FT4 ");
    s.sync();
    const AutoDxRuntimeConfig stringListModes = AutoDxRuntimeConfig::load(temp.path());
    assert(stringListModes.modes == (QStringList() << "FT8" << "FT4"));

    s.setValue("AutoDx/Modes", "FT4");
    s.sync();
    const AutoDxRuntimeConfig ft4Mode = AutoDxRuntimeConfig::load(temp.path());
    assert(ft4Mode.modes == (QStringList() << "FT4"));
    assert(!ft4Mode.effectiveEnabled("FT8"));
    assert(ft4Mode.effectiveEnabled("FT4"));

    s.setValue("AutoDx/ATNOChaseType", 99);
    s.setValue("AutoDx/ScarceThreshold", -5);
    s.setValue("AutomationTiming/NormalCallSeconds", 1);
    s.setValue("AutomationTiming/QuietBandSeconds", 99999);
    s.setValue("AutomationTiming/QuietBandEmptyPeriods", 999);
    s.setValue("AutomationTiming/TargetHeardFreshSeconds", 1);
    s.setValue("AutomationTiming/CrossBandVerifySeconds", 99999);
    s.setValue("AutomationTiming/BandSwitchCooldownSeconds", -1);
    s.setValue("Attempt/RecentQsoCooldownSeconds", 99999);
    s.setValue("Attempt/EngagedCompletionGraceSeconds", 999);
    s.setValue("Attempt/ATNOMinimumCallMinutes", 999);
    s.setValue("ReferenceHunting/MaxActivationAgeSeconds", 999999);
    s.setValue("PropagationAdaptation/WindowSeconds", 999999);
    s.setValue("PropagationAdaptation/UniqueDecodeWeight", 999999);
    s.setValue("PropagationAdaptation/DistantDecodeWeight", 999999);
    s.setValue("PropagationAdaptation/SuccessfulQsoWeight", 999999);
    s.setValue("PropagationAdaptation/MaxBandBoost", 999999);
    s.setValue("PileupStrategy/AudioOffsetsHz", "-9999,0,0,9999");
    s.setValue("PileupStrategy/RevisitDelaySeconds", 999999);
    s.setValue("DirectedCallers/InboxSize", 999);
    s.setValue("DirectedCallers/MaxAgeSeconds", 99999);
    s.sync();
    const AutoDxRuntimeConfig bounded = AutoDxRuntimeConfig::load(temp.path());
    assert(bounded.atnoChaseType == 3);
    assert(bounded.scarceThreshold == 0);
    assert(bounded.normalCallSeconds == 30 && bounded.quietBandSeconds == 3600);
    assert(bounded.quietBandEmptyPeriods == 6);
    assert(bounded.targetHeardFreshSeconds == 15 && bounded.crossBandVerifySeconds == 300);
    assert(bounded.bandSwitchCooldownSeconds == 0);
    assert(bounded.selection.recentQsoCooldownSeconds == 86400);
    assert(bounded.engagedCompletionGraceSeconds == 120);
    assert(bounded.atnoMinimumCallSeconds == 10800);
    assert(bounded.awardHunting.maxActivationAgeSeconds == 86400);
    assert(bounded.propagationAdaptation.windowSeconds == 86400);
    assert(bounded.propagationAdaptation.uniqueDecodeWeight == 100000);
    assert(bounded.propagationAdaptation.distantDecodeWeight == 100000);
    assert(bounded.propagationAdaptation.successfulQsoWeight == 100000);
    assert(bounded.propagationAdaptation.maxBandBoost == 100000);
    assert(bounded.pileupStrategy.audioOffsetsHz
        == (QList<int>() << -2400 << 0 << 2400));
    assert(bounded.pileupStrategy.revisitDelaySeconds == 86400);
    assert(bounded.directedCallerInboxSize == 100);
    assert(bounded.directedCallerMaxAgeSeconds == 3600);

    // Missing config is safe: no desired automation, no cross-band switching,
    // FT8 and FT4 are the allowed planner modes, and bounded defaults are retained.
    QTemporaryDir empty;
    const AutoDxRuntimeConfig defaults = AutoDxRuntimeConfig::load(empty.path());
    assert(!defaults.desiredEnabled && !defaults.bandSwitchingEnabled);
    assert(defaults.modes == (QStringList() << "FT8" << "FT4"));
    assert(!defaults.effectiveEnabled("FT8"));
    assert(defaults.minSnr == -20 && defaults.scarceThreshold == 5);
    assert(defaults.normalCallSeconds == 120 && defaults.quietBandSeconds == 300);
    assert(defaults.quietBandEmptyPeriods == 5);
    assert(defaults.targetHeardFreshSeconds == 60 && defaults.crossBandVerifySeconds == 60);
    assert(defaults.bandSwitchCooldownSeconds == 120);
    assert(defaults.selection.recentQsoCooldownSeconds == 3600);
    assert(defaults.engagedCompletionGraceSeconds == 120);
    assert(defaults.atnoMinimumCallSeconds == 1800);
    assert(AutoDxTimingPolicy::attemptLimitSeconds(true, true, 120, 1800) == 1800);
    assert(!AutoDxTimingPolicy::emptyDecodePeriodsExpired(4, 5));
    assert(AutoDxTimingPolicy::emptyDecodePeriodsExpired(5, 5));
    assert(AutoDxTimingPolicy::attemptLimitSeconds(true, false, 120, 1800) == 120);
    assert(AutoDxTimingPolicy::attemptLimitSeconds(false, true, 120, 1800) == 120);
    assert(defaults.persistNewDxccWhileHeard && defaults.persistNewBandSlotWhileHeard);
    assert(!defaults.selection.filterMatrixEnabled && defaults.selection.preferNonEurope);
    assert(defaults.selection.nonEuropeBoost == 7500);
    assert(defaults.selection.filterNewCall && defaults.selection.filterNewDxcc
           && defaults.selection.filterNewGrid);
    assert(!defaults.selection.filterNewContinent && !defaults.selection.filterNewCqZone
           && !defaults.selection.filterNewItuZone);
    assert(defaults.selection.filterBandCall && defaults.selection.filterBandGrid);
    assert(defaults.selection.allowBandDxccOutsideContinent);
    assert(!defaults.selection.filterBandDxcc && !defaults.selection.filterBandContinent
           && !defaults.selection.filterBandCqZone && !defaults.selection.filterBandItuZone);
    assert(defaults.selection.minSignal == -20);
    assert(!defaults.selection.lotwOnly && !defaults.selection.treat73AsCq
           && defaults.selection.watchUnconfirmedDxcc);
    assert(defaults.excludedCountriesByBand.isEmpty());
    assert(defaults.selection.selectionOrder == "score");
    assert(defaults.selection.callWindowSeconds == 120);
    assert(defaults.selection.maxConsecutiveWindows == 1);
    assert(defaults.selection.sameTargetRetrySeconds == 1800);
    assert(defaults.selection.minimumBandDwellSeconds == 180);
    assert(defaults.dxpeditionChaseEnabled);
    assert(defaults.dxpeditionAllowSameBandOffStandardQsy);
    assert(defaults.dxpeditionAllowCrossBandQsy);
    assert(!defaults.dxpeditionChaseAnyActive);
    assert(defaults.dxpeditionMinSpotters == 1);
    assert(defaults.dxpeditionMaxSpotAgeSeconds == 120);
    assert(defaults.dxpeditionTxOffsetHz == 1000);
    assert(defaults.dxpeditionReturnToStandard);
    assert(defaults.awardHunting.enabled && defaults.awardHunting.referenceEnabled);
    assert(defaults.awardHunting.potaEnabled && defaults.awardHunting.sotaEnabled
           && defaults.awardHunting.wwffEnabled);
    assert(defaults.awardHunting.newReferenceWeight == 2500);
    assert(defaults.propagationAdaptation.enabled
           && defaults.propagationAdaptation.windowSeconds == 900);
    assert(defaults.pileupStrategy.audioFrequency(1500, 2) == 1380);
    assert(defaults.directedCallersEnabled && defaults.directedCallerInboxSize == 8);
    assert(defaults.campaignProfile == "balanced" && defaults.outcomeLearningEnabled);

    QTemporaryDir awards;
    assert(awards.isValid());
    QFile awardFile(awards.path() + "/award_hunting.json");
    assert(awardFile.open(QIODevice::WriteOnly));
    const QByteArray awardJson = QByteArray(
        "{\"schema\":1,\"history_authoritative\":true,\"activations\":[{\"callsign\":\"K1ABC\","
        "\"program\":\"POTA\",\"reference\":\"K-0001\",\"band\":\"40m\","
        "\"mode\":\"FT8\",\"frequency_hz\":7074000,"
        "\"spotted_at_utc\":\"2030-01-01T00:00:00Z\","
        "\"expires_at_utc\":\"2030-01-01T01:00:00Z\",\"source_id\":\"fixture\","
        "\"confidence\":0.9,\"slot_key\":\"POTA:K-0001@40m@FT8\",\"history_status\":\"authoritative\","
        "\"gaps\":{\"new_reference\":true,\"new_reference_on_band\":true,"
        "\"new_reference_on_band_mode\":true}}]}");
    assert(awardFile.write(awardJson) == awardJson.size());
    awardFile.close();
    AwardActivationIndex awardIndex;
    assert(awardIndex.load(awardFile.fileName()));
    assert(awardIndex.schemaValid() && awardIndex.entryCount() == 1);
    AwardHuntingConfig awardConfig;
    const AwardReferenceScore awardScore = awardIndex.score(
        "K1ABC", "40m", "FT8", true,
        QDateTime::fromString("2030-01-01T00:05:00Z", Qt::ISODate), awardConfig);
    assert(awardScore.eligible && awardScore.program == "POTA");
    assert(awardScore.score == 1800 + 2500 + 1000 + 500);
    awardConfig.sotaEnabled = false;
    awardConfig.referenceWeightPercent = 50;
    assert(awardIndex.score("K1ABC", "40m", "FT8", true,
        QDateTime::fromString("2030-01-01T00:05:00Z", Qt::ISODate), awardConfig).score
        == awardScore.score / 2);
    awardConfig.requireLocalDecode = true;
    assert(!awardIndex.score("K1ABC", "40m", "FT8", false,
        QDateTime::fromString("2030-01-01T00:05:00Z", Qt::ISODate), awardConfig).eligible);
    assert(awardFile.open(QIODevice::WriteOnly | QIODevice::Truncate));
    QByteArray noGapJson = awardJson;
    noGapJson.replace("\"new_reference\":true", "\"new_reference\":false");
    noGapJson.replace("\"new_reference_on_band\":true", "\"new_reference_on_band\":false");
    noGapJson.replace("\"new_reference_on_band_mode\":true", "\"new_reference_on_band_mode\":false");
    assert(awardFile.write(noGapJson) == noGapJson.size());
    awardFile.close();
    assert(awardIndex.load(awardFile.fileName()));
    assert(!awardIndex.score("K1ABC", "40m", "FT8", true,
        QDateTime::fromString("2030-01-01T00:05:00Z", Qt::ISODate), awardConfig).eligible);

    QTemporaryDir legacyGrace;
    QSettings legacy(legacyGrace.path() + "/autodx.ini", QSettings::IniFormat);
    legacy.setValue("AutoDX/EngagedCompletionGraceSeconds", 31);
    legacy.sync();
    assert(AutoDxRuntimeConfig::load(legacyGrace.path())
        .engagedCompletionGraceSeconds == 45);

    QTemporaryDir bands;
    assert(bands.isValid());
    const QString bandsPath = bands.path() + "/autodx.ini";
    const QList<int> expectedBands = QList<int>() << 3 << 4 << 6 << 7 << 8 << 9 << 10 << 11 << 12;
    for (const QByteArray &encoded : {
             QByteArray("[BandSelection]\nEnabledBands=3,4,6,7,8,9,10,11,12\n"),
             QByteArray("[BandSelection]\nEnabledBands=\"3,4,6,7,8,9,10,11,12\"\n")}) {
        QFile file(bandsPath);
        assert(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        assert(file.write(encoded) == encoded.size());
        file.close();
        BandManager manager;
        manager.loadSettings(bands.path());
        assert(manager.getEnabledBands() == expectedBands);
        assert(manager.bandSchedule(3).restricted);
        assert(manager.bandSchedule(3).start == QTime(18, 0));
        assert(manager.bandSchedule(3).end == QTime(6, 0));
        assert(manager.isBandOpenAt(3, QTime(23, 0)));
        assert(manager.isBandOpenAt(3, QTime(5, 59)));
        assert(!manager.isBandOpenAt(3, QTime(12, 0)));
        assert(!manager.bandSchedule(8).restricted);
        assert(manager.isBandOpenAt(8, QTime(12, 0)));
    }

    QSettings bandSettings(bandsPath, QSettings::IniFormat);
    bandSettings.setValue("BandSchedules/Band8Restricted", true);
    bandSettings.setValue("BandSchedules/Band8Start", "09:30");
    bandSettings.setValue("BandSchedules/Band8End", "17:15");
    bandSettings.sync();
    BandManager scheduled;
    scheduled.loadSettings(bands.path());
    assert(scheduled.isBandOpenAt(8, QTime(9, 30)));
    assert(scheduled.isBandOpenAt(8, QTime(17, 14)));
    assert(!scheduled.isBandOpenAt(8, QTime(17, 15)));
    std::cout << "AutoDX runtime config behavior passed" << std::endl;
    return 0;
}
