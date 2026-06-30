import Combine
import Foundation

@MainActor
final class StatsViewModel: ObservableObject {
    @Published var stats: Stats = .empty
    @Published var exportMessage: String?

    private let store: LifeOSStore
    private var cancellables: Set<AnyCancellable> = []

    init(store: LifeOSStore) {
        self.store = store

        store.$dayLogs
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in
                self?.stats = store.stats
            }
            .store(in: &cancellables)

        stats = store.stats
    }

    var last30Points: [DailyProductivityPoint] {
        Array(stats.points.suffix(30))
    }

    func exportJSON() {
        do {
            let url = try store.exportData()
            exportMessage = "Данные экспортированы: \(url.lastPathComponent)"
        } catch ExportError.cancelled {
            exportMessage = "Экспорт отменён"
        } catch {
            exportMessage = "Ошибка экспорта: \(error.localizedDescription)"
        }
    }
}
