#include "HvAutoDxer/autodxhistoryconditional.h"

#include <cassert>

int main()
{
    const QByteArray cached("\"0123456789abcdef\"");
    assert(AutoDxHistoryConditional::hasExactEntityTag(cached, cached));
    assert(!AutoDxHistoryConditional::hasExactEntityTag(QByteArray(), cached));
    assert(!AutoDxHistoryConditional::hasExactEntityTag(cached, QByteArray()));
    assert(!AutoDxHistoryConditional::hasExactEntityTag(
        QByteArray("\"different\""), cached));
    return 0;
}
