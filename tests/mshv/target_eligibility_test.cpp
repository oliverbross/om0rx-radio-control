#include <cassert>
#include "targeteligibility.h"

int main()
{
    const int dxcc = 10000;
    const int band = 1000;
    const int grid = 500;
    const int calling = 400;

    TargetEligibility newGridOnWorkedBand(false, false, true, false);
    assert(newGridOnWorkedBand.any());
    assert(newGridOnWorkedBand.weightedScore(dxcc, band, grid, calling) == grid);

    TargetEligibility dxccBandGrid(true, true, true, false);
    assert(dxccBandGrid.any());
    assert(dxccBandGrid.weightedScore(dxcc, band, grid, calling) == dxcc + band + grid);

    TargetEligibility allDimensions(true, true, true, true);
    assert(allDimensions.weightedScore(dxcc, band, grid, calling) == dxcc + band + grid + calling);

    TargetEligibility randomWorked(false, false, false, false);
    assert(!randomWorked.any());
    assert(randomWorked.weightedScore(dxcc, band, grid, calling) == 0);

    return 0;
}
