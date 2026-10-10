#include <cassert>

#include "om0rxtxwatchdogedge.h"

int main()
{
    // Normal native TX -> RX advances the edge generation and is completion,
    // never a watchdog fault.
    assert(!Om0rxTxWatchdogEdge::shouldTrip(false, 1, 2));
    assert(!Om0rxTxWatchdogEdge::shouldTrip(true, 1, 2));

    // Only continuously asserted PTT from the exact armed edge may trip.
    assert(Om0rxTxWatchdogEdge::shouldTrip(true, 7, 7));
    assert(!Om0rxTxWatchdogEdge::shouldTrip(false, 7, 7));
    return 0;
}
