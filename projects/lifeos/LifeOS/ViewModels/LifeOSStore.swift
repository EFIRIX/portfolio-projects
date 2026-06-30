import Combine
import Foundation

@MainActor
final class LifeOSStore: ObservableObject {
    @Published var dayLogs: [DayLog] = []
    @Published var goals: [Goal] = []
    @Published var errorMessage: String?

    private let database: SQLiteDatabase?
    private let scoringService = ProductivityScoringService()
    private let analysisService = AIAnalysisService()
    private let statsService = StatsService()
    private let levelService = LevelService()
    private let exportService = ExportService()

    init() {
        do {
            self.database = try SQLiteDatabase()
        } catch {
            self.database = nil
            self.errorMessage = error.localizedDescription
            return
        }

        do {
            try readFromDatabase()
        } catch {
            self.errorMessage = error.localizedDescription
        }
    }

    func loadData() {
        do {
            try readFromDatabase()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func log(for date: Date) -> DayLog? {
        dayLogs.first { $0.date.isSameDay(as: date) }
    }

    func upsertLog(draft: DayLogDraft, date: Date = Date()) {
        do {
            let score = scoringService.calculateScore(from: draft)
            var log = DayLog(
                date: date.startOfDayValue,
                readingMinutes: draft.readingMinutes,
                deepWorkHours: draft.deepWorkHours,
                workout: draft.workout,
                learning: draft.learning,
                sleepHours: draft.sleepHours,
                mood: draft.mood,
                score: score,
                analysis: ""
            )

            let merged = mergedLogs(with: log)
            let streak = statsService.currentStreak(logs: merged)
            log.analysis = analysisService.generateAnalysis(for: log, streak: streak)

            try database?.upsertDayLog(log)
            try readFromDatabase()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func updateLog(_ log: DayLog) {
        let draft = DayLogDraft(from: log)
        upsertLog(draft: draft, date: log.date)
    }

    func upsertGoal(_ goal: Goal) {
        do {
            try database?.upsertGoal(goal)
            try readFromDatabase()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteGoal(_ goal: Goal) {
        do {
            try database?.deleteGoal(id: goal.id)
            try readFromDatabase()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    var stats: Stats {
        statsService.buildStats(logs: dayLogs)
    }

    var userLevel: UserProductivityLevel {
        levelService.resolveLevel(
            averageScore: stats.averageIndex,
            streak: stats.currentStreak
        )
    }

    func ringProgress(for date: Date) -> (focus: Double, growth: Double, discipline: Double) {
        let draft: DayLogDraft
        if let log = log(for: date) {
            draft = DayLogDraft(from: log)
        } else {
            draft = .default
        }

        return scoringService.ringProgress(from: draft)
    }

    func score(for date: Date) -> ProductivityScore {
        ProductivityScore(value: log(for: date)?.score ?? 0)
    }

    func heatmapCells(weeks: Int = 52) -> [HeatmapDay] {
        let totalDays = weeks * 7
        let endDate = Date().startOfDayValue
        let startDate = endDate.addingDays(-(totalDays - 1))

        return (0 ..< totalDays).map { offset in
            let date = startDate.addingDays(offset)
            let score = log(for: date)?.score ?? 0
            return HeatmapDay(
                date: date,
                score: score,
                intensity: scoringService.heatmapIntensity(for: score)
            )
        }
    }

    func exportData() throws -> URL {
        try exportService.exportJSON(dayLogs: dayLogs, goals: goals)
    }

    private func mergedLogs(with newLog: DayLog) -> [DayLog] {
        var dictionary = Dictionary(uniqueKeysWithValues: dayLogs.map { ($0.date.dayKey, $0) })
        dictionary[newLog.date.dayKey] = newLog
        return Array(dictionary.values)
    }

    private func readFromDatabase() throws {
        guard let database else { return }
        dayLogs = try database.fetchAllDayLogs()
        goals = try database.fetchGoals()
    }
}
