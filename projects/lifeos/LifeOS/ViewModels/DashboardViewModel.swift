import Combine
import Foundation

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published var heatmap: [HeatmapDay] = []
    @Published var todayScore = ProductivityScore(value: 0)
    @Published var focusProgress: Double = 0
    @Published var growthProgress: Double = 0
    @Published var disciplineProgress: Double = 0
    @Published var levelTitle: String = UserProductivityLevel.novice.title
    @Published var analysis: String = "Добавьте первый отчёт, чтобы получить AI-анализ дня."

    private let store: LifeOSStore
    private var cancellables: Set<AnyCancellable> = []

    init(store: LifeOSStore) {
        self.store = store

        store.$dayLogs
            .combineLatest(store.$goals)
            .receive(on: RunLoop.main)
            .sink { [weak self] _, _ in
                self?.reload()
            }
            .store(in: &cancellables)

        reload()
    }

    func reload() {
        heatmap = store.heatmapCells()
        todayScore = store.score(for: Date())

        let ring = store.ringProgress(for: Date())
        focusProgress = ring.focus
        growthProgress = ring.growth
        disciplineProgress = ring.discipline

        levelTitle = store.userLevel.title
        analysis = store.log(for: Date())?.analysis ?? "Сегодня ещё нет отчёта. Заполните данные, и система соберёт персональный анализ дня."
    }

    func log(for date: Date) -> DayLog? {
        store.log(for: date)
    }
}
