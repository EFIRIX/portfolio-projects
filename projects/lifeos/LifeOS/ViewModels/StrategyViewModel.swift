import Combine
import Foundation

@MainActor
final class StrategyViewModel: ObservableObject {
    @Published var goals: [Goal] = []

    private let store: LifeOSStore
    private var cancellables: Set<AnyCancellable> = []

    init(store: LifeOSStore) {
        self.store = store

        store.$goals
            .receive(on: RunLoop.main)
            .sink { [weak self] goals in
                self?.goals = goals
            }
            .store(in: &cancellables)

        goals = store.goals
    }

    var activeProjects: [Goal] {
        goals.filter { $0.progress < 100 }
    }

    var averageProgress: Double {
        guard !goals.isEmpty else { return 0 }
        let total = goals.reduce(0) { $0 + $1.progress }
        return Double(total) / Double(goals.count)
    }

    func saveGoal(_ goal: Goal) {
        store.upsertGoal(goal)
    }

    func deleteGoal(_ goal: Goal) {
        store.deleteGoal(goal)
    }
}
