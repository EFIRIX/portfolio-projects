import SwiftUI

struct ContentView: View {

    let rows = 20
    let cols = 20
    let cellSize: CGFloat = 16

    @State private var world: [[Int]] = []
    @State private var playerX = 10
    @State private var playerY = 5
    @State private var velocityY = 0
    @State private var wood = 0
    @State private var timer: Timer?
    @State private var gameOver = false
    @State private var worldReady = false

    var body: some View {
        VStack {

            Text("🌤 SkyBlock")
                .font(.largeTitle)

            Text("🪵 Wood: \(wood)")

            ZStack {
                Color.cyan.opacity(0.3)

                if worldReady {
                    worldView
                    playerView
                }

                if gameOver {
                    VStack {
                        Text("You fell ☠️")
                            .font(.largeTitle)
                            .foregroundColor(.red)

                        Button("Restart") {
                            restartGame()
                        }
                    }
                }
            }
            .frame(width: CGFloat(cols) * cellSize,
                   height: CGFloat(rows) * cellSize)

            controls
        }
        .onAppear {
            generateWorld()
            startGameLoop()
        }
    }

    // 🌍 Мир
    var worldView: some View {
        VStack(spacing: 0) {
            ForEach(0..<rows, id: \.self) { y in
                HStack(spacing: 0) {
                    ForEach(0..<cols, id: \.self) { x in
                        Rectangle()
                            .fill(colorFor(x: x, y: y))
                            .frame(width: cellSize, height: cellSize)
                    }
                }
            }
        }
    }

    // 👤 Игрок
    var playerView: some View {
        Rectangle()
            .fill(Color.red)
            .frame(width: cellSize, height: cellSize)
            .offset(
                x: CGFloat(playerX) * cellSize,
                y: CGFloat(playerY) * cellSize
            )
    }

    // 🎮 Кнопки
    var controls: some View {
        HStack(spacing: 20) {
            Button("⬅️") { move(dx: -1) }
            Button("⬆️ Jump") { jump() }
            Button("➡️") { move(dx: 1) }
            Button("⛏ Mine") { mine() }
        }
        .font(.title2)
    }

    // 🧱 SAFE доступ к блоку
    func blockAt(x: Int, y: Int) -> Int {
        guard y >= 0,
              y < world.count,
              x >= 0,
              x < world[y].count else {
            return 0
        }
        return world[y][x]
    }

    // 🎨 Цвет клетки
    func colorFor(x: Int, y: Int) -> Color {
        switch blockAt(x: x, y: y) {
        case 1: return .brown
        case 2: return .orange
        default: return .clear
        }
    }

    // 🌍 Генерация острова
    func generateWorld() {
        world = Array(
            repeating: Array(repeating: 0, count: cols),
            count: rows
        )

        for x in 7...12 {
            world[12][x] = 1
            world[13][x] = 1
        }

        world[11][10] = 2
        world[10][10] = 2

        worldReady = true
    }

    // 🕹 Движение
    func move(dx: Int) {
        let newX = playerX + dx
        if newX >= 0 && newX < cols {
            playerX = newX
        }
    }

    func jump() {
        if isOnGround() {
            velocityY = -3
        }
    }

    func mine() {
        let targetY = playerY + 1

        if blockAt(x: playerX, y: targetY) == 2 {
            wood += 1
        }

        if targetY >= 0 && targetY < rows {
            world[targetY][playerX] = 0
        }
    }

    // ⚙️ Физика
    func startGameLoop() {
        timer?.invalidate()

        timer = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { _ in
            applyPhysics()
        }
    }

    func applyPhysics() {
        guard !gameOver else { return }

        velocityY += 1
        var newY = playerY + velocityY

        if blockAt(x: playerX, y: newY) != 0 {
            velocityY = 0
            newY -= 1
        }

        playerY = newY

        if playerY >= rows {
            gameOver = true
        }
    }

    func isOnGround() -> Bool {
        blockAt(x: playerX, y: playerY + 1) != 0
    }

    // 🔄 Рестарт
    func restartGame() {
        playerX = 10
        playerY = 5
        velocityY = 0
        wood = 0
        gameOver = false
        generateWorld()
    }
}
