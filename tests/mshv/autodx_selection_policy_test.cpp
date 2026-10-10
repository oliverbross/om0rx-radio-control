#include <cassert>
#include "autodxselectionpolicy.h"

int main()
{
    AutoDxSelectionConfig defaults;
    assert(!defaults.filterMatrixEnabled);
    assert(defaults.filterNewCall && defaults.filterNewDxcc && defaults.filterNewGrid);
    assert(!defaults.filterNewContinent && !defaults.filterNewCqZone
           && !defaults.filterNewItuZone);
    assert(defaults.filterBandCall && defaults.filterBandGrid);
    assert(defaults.allowBandDxccOutsideContinent);
    assert(!defaults.filterBandDxcc && !defaults.filterBandContinent
           && !defaults.filterBandCqZone && !defaults.filterBandItuZone);
    assert(defaults.preferNonEurope && defaults.nonEuropeBoost == 7500);
    assert(defaults.minSignal == -20);
    assert(defaults.callWindowSeconds == 120);
    assert(defaults.maxConsecutiveWindows == 1);
    assert(defaults.sameTargetRetrySeconds == 1800);
    assert(defaults.minimumBandDwellSeconds == 180);
    assert(defaults.totalAttemptBudgetSeconds() == 120);
    assert(!AutoDxSelectionConfig::isCqOr73("OM0RX K1ABC 73", false));
    assert(AutoDxSelectionConfig::isCqOr73("OM0RX K1ABC 73", true));
    assert(AutoDxSelectionConfig::isCqOr73("OM0RX K1ABC RR73", true));

    AutoDxSelectionConfig matrix;
    matrix.filterMatrixEnabled = true;
    matrix.filterNewCall = true;
    matrix.filterBandCall = false;
    matrix.filterBandGrid = false;
    matrix.preferNonEurope = true;
    matrix.nonEuropeBoost = 7500;
    matrix.minSignal = -18;

    AutoDxEligibilityFacts asia;
    asia.newCall = true;
    asia.continent = "AS";
    asia.snr = -10;
    AutoDxEligibilityResult eligible = matrix.evaluate(asia);
    assert(eligible.eligible);
    assert(eligible.targetClass == "new-call");
    assert(eligible.scoreBoost == 7500);

    AutoDxEligibilityFacts europe = asia;
    europe.continent = "EU";
    assert(matrix.evaluate(europe).scoreBoost == 0);
    europe.snr = -19;
    assert(!matrix.evaluate(europe).eligible);

    matrix.enabledContinents.remove("EU");
    europe.snr = -10;
    assert(matrix.evaluate(europe).blockers.contains("continent-disabled"));

    // A new DXCC band slot may explicitly override continent filtering on
    // every band, while disabling the option restores the continent block.
    europe.bandDxcc = true;
    AutoDxEligibilityResult bandDxccOverride = matrix.evaluate(europe);
    assert(bandDxccOverride.eligible);
    assert(bandDxccOverride.targetClass == "band-dxcc");
    assert(bandDxccOverride.reasons.contains("continent-filter-override"));
    matrix.allowBandDxccOutsideContinent = false;
    assert(matrix.evaluate(europe).blockers.contains("continent-disabled"));
    matrix.allowBandDxccOutsideContinent = true;

    matrix.lotwOnly = true;
    asia.lotwKnown = false;
    assert(matrix.evaluate(asia).eligible); // absent data is not fabricated
    asia.lotwKnown = true;
    asia.lotwMember = false;
    assert(matrix.evaluate(asia).blockers.contains("lotw-only"));

    AutoDxEligibilityFacts caller;
    caller.directedCaller = true;
    caller.snr = -40;
    caller.continent = "EU";
    assert(matrix.evaluate(caller).eligible); // directed callers preempt filters

    assert(!matrix.canLeaveBand(179999, false, false, false));
    assert(matrix.canLeaveBand(0, true, false, false));
    assert(matrix.canLeaveBand(0, false, true, false));
    assert(matrix.canLeaveBand(0, false, false, true));
    assert(matrix.canLeaveBand(180000, false, false, false));

    matrix.callWindowSeconds = 240;
    matrix.maxConsecutiveWindows = 3;
    assert(matrix.totalAttemptBudgetSeconds() == 720);

    // One busy band contributes one place in the rotation regardless of how
    // many distinct calls it supplies. Bands excluded by schedule/backoff are
    // removed before this helper is invoked and cannot move the cursor.
    const QList<int> continuous80m = QList<int>() << 4 << 4 << 4 << 6 << 8 << 10;
    assert(AutoDxCrossBandFairness::chooseBand(continuous80m, -1) == 4);
    assert(AutoDxCrossBandFairness::chooseBand(continuous80m, 4) == 6);
    assert(AutoDxCrossBandFairness::chooseBand(continuous80m, 6) == 8);
    assert(AutoDxCrossBandFairness::chooseBand(continuous80m, 8) == 10);
    assert(AutoDxCrossBandFairness::chooseBand(continuous80m, 10) == 4);
    const QList<int> scheduleFiltered = QList<int>() << 4 << 8 << 10;
    assert(AutoDxCrossBandFairness::chooseBand(scheduleFiltered, 4) == 8);
    assert(AutoDxCrossBandFairness::chooseBand(QList<int>(), 4) == -1);
    return 0;
}
