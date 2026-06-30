import Combine
import Foundation

@MainActor
final class DayDetailViewModel: ObservableObject {
    @Published var date: Date
    @Published var draft: DayLogDraft = .default
    @Published var score = ProductivityScore(value: 0)
    @Published var analysis: String = "Нет данных"
    @Published var isExistingLog = false
    @Published var saveMessage: String?

    private let store: LifeOSStore
    private var cancellables: Set<AnyCancellable> = []

    init(store: LifeOSStore, date: Date) {
        self.store = store
        self.date = date.startOfDayValue

        store.$dayLogs
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in
                self?.reload()
            }
            .store(in: &cancellables)

        reload()
    }

    func reload() {
        if let log = store.log(for: date) {
            draft = DayLogDraft(from: log)
            score = ProductivityScore(value: log.score)
            analysis = log.analysis
            isExistingLog = true
        } else {
            draft = .default
            score = ProductivityScore(value: 0)
            analysis = "На этот день ещё нет отчёта."
            isExistingLog = false
        }
    }

    func save() {
        store.upsertLog(draft: draft, date: date)
        reload()
        if let errorMessage = store.errorMessage {
            saveMessage = "Ошибка: \(errorMessage)"
        } else {
            saveMessage = "Изменения сохранены"
        }
    }
}
