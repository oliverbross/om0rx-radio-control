#ifndef OM0RX_FAKE_TARGET_SCORER_DEPENDENCIES_H
#define OM0RX_FAKE_TARGET_SCORER_DEPENDENCIES_H

#include <QMap>
#include <QString>
#include "autodxselectionpolicy.h"

// Narrow deterministic fixture for the production TargetScorer.  The scorer
// still compiles from the maintained MSHV source; only its hardware/log-backed
// tracker dependency is replaced so worked/new combinations can be asserted.
class DxccTracker
{
public:
    void setCallStatus(const QString &call, bool newDxcc, bool newBandSlot)
    {
        m_newDxcc.insert(call.toUpper(), newDxcc);
        m_newBandSlot.insert(call.toUpper(), newBandSlot);
    }

    void setGridStatus(const QString &grid, bool isNew)
    {
        m_newGrid.insert(grid.left(4).toUpper(), isNew);
    }

    void setEligibilityFacts(const QString &call, const AutoDxEligibilityFacts &facts)
    {
        m_facts.insert(call.toUpper(), facts);
    }

    void setCallWorkedSlot(const QString &call, bool worked)
    {
        m_workedSlot.insert(call.toUpper(), worked);
    }

    void setConfirmationStatus(const QString &call, bool dxccConfirmed,
                               bool bandModeConfirmed)
    {
        m_confirmedDxcc.insert(call.toUpper(), dxccConfirmed);
        m_confirmedBandMode.insert(call.toUpper(), bandModeConfirmed);
    }

    bool isDxccConfirmedByCall(const QString &call) const
    {
        return m_confirmedDxcc.value(call.toUpper(), false);
    }

    bool isDxccConfirmedBandModeByCall(const QString &call, int,
                                       const QString &) const
    {
        return m_confirmedBandMode.value(call.toUpper(), false);
    }

    bool isNewDXCCByCall(const QString &call) const
    {
        ++dxccQueries;
        return m_newDxcc.value(call.toUpper(), false);
    }

    bool isNewBandSlotByCall(const QString &call, int) const
    {
        ++bandQueries;
        return m_newBandSlot.value(call.toUpper(), false);
    }

    bool isNewGrid(const QString &grid) const
    {
        ++gridQueries;
        return m_newGrid.value(grid.left(4).toUpper(), false);
    }

    AutoDxEligibilityFacts eligibilityFacts(const QString &call,
                                             const QString &grid,
                                             int) const
    {
        ++dxccQueries;
        ++bandQueries;
        ++gridQueries;
        AutoDxEligibilityFacts facts;
        if (m_facts.contains(call.toUpper())) facts = m_facts.value(call.toUpper());
        else facts.bandCall = !m_workedSlot.value(call.toUpper(), false);
        facts.newDxcc = m_newDxcc.value(call.toUpper(), false);
        facts.bandDxcc = m_newBandSlot.value(call.toUpper(), false);
        facts.newGrid = m_newGrid.value(grid.left(4).toUpper(), false);
        facts.bandGrid = facts.newGrid;
        facts.continent = call.startsWith("EU") ? "EU" : "NA";
        return facts;
    }

    mutable int dxccQueries = 0;
    mutable int bandQueries = 0;
    mutable int gridQueries = 0;

private:
    QMap<QString, bool> m_newDxcc;
    QMap<QString, bool> m_newBandSlot;
    QMap<QString, bool> m_newGrid;
    QMap<QString, AutoDxEligibilityFacts> m_facts;
    QMap<QString, bool> m_workedSlot;
    QMap<QString, bool> m_confirmedDxcc;
    QMap<QString, bool> m_confirmedBandMode;
};

class HvCty
{
public:
    QString FindCountry(const QString &, bool) const { return QStringLiteral("Fixture Entity"); }
};

#endif
