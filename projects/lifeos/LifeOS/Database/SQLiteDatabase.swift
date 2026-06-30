import Foundation
import SQLite3

enum DatabaseError: LocalizedError {
    case openFailed(message: String)
    case statementFailed(message: String)
    case executionFailed(message: String)

    var errorDescription: String? {
        switch self {
        case .openFailed(let message):
            return "Не удалось открыть базу данных: \(message)"
        case .statementFailed(let message):
            return "Ошибка подготовки SQL: \(message)"
        case .executionFailed(let message):
            return "Ошибка выполнения SQL: \(message)"
        }
    }
}

final class SQLiteDatabase {
    private let db: OpaquePointer
    private let queue = DispatchQueue(label: "lifeos.sqlite.queue")
    private let sqliteTransient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

    init() throws {
        self.db = try Self.openDatabase()
        try createTables()
    }

    deinit {
        sqlite3_close(db)
    }

    func upsertDayLog(_ log: DayLog) throws {
        try queue.sync {
            let sql = """
            INSERT INTO day_logs (
                date_key,
                date_ts,
                reading_minutes,
                deep_work_hours,
                workout,
                learning,
                sleep_hours,
                mood,
                score,
                analysis
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date_key) DO UPDATE SET
                date_ts = excluded.date_ts,
                reading_minutes = excluded.reading_minutes,
                deep_work_hours = excluded.deep_work_hours,
                workout = excluded.workout,
                learning = excluded.learning,
                sleep_hours = excluded.sleep_hours,
                mood = excluded.mood,
                score = excluded.score,
                analysis = excluded.analysis;
            """

            let statement = try prepareStatement(sql)
            defer { sqlite3_finalize(statement) }

            sqlite3_bind_text(statement, 1, (log.date.dayKey as NSString).utf8String, -1, sqliteTransient)
            sqlite3_bind_double(statement, 2, log.date.startOfDayValue.timeIntervalSince1970)
            sqlite3_bind_int(statement, 3, Int32(log.readingMinutes))
            sqlite3_bind_double(statement, 4, log.deepWorkHours)
            sqlite3_bind_int(statement, 5, log.workout ? 1 : 0)
            sqlite3_bind_int(statement, 6, log.learning ? 1 : 0)
            sqlite3_bind_double(statement, 7, log.sleepHours)
            sqlite3_bind_int(statement, 8, Int32(log.mood))
            sqlite3_bind_int(statement, 9, Int32(log.score))
            sqlite3_bind_text(statement, 10, (log.analysis as NSString).utf8String, -1, sqliteTransient)

            guard sqlite3_step(statement) == SQLITE_DONE else {
                throw DatabaseError.executionFailed(message: sqliteErrorMessage())
            }
        }
    }

    func dayLog(for date: Date) throws -> DayLog? {
        try queue.sync {
            let sql = """
            SELECT date_ts, reading_minutes, deep_work_hours, workout, learning, sleep_hours, mood, score, analysis
            FROM day_logs
            WHERE date_key = ?
            LIMIT 1;
            """

            let statement = try prepareStatement(sql)
            defer { sqlite3_finalize(statement) }

            sqlite3_bind_text(statement, 1, (date.dayKey as NSString).utf8String, -1, sqliteTransient)

            if sqlite3_step(statement) == SQLITE_ROW {
                return parseDayLogRow(from: statement)
            }

            return nil
        }
    }

    func fetchAllDayLogs() throws -> [DayLog] {
        try queue.sync {
            let sql = """
            SELECT date_ts, reading_minutes, deep_work_hours, workout, learning, sleep_hours, mood, score, analysis
            FROM day_logs
            ORDER BY date_ts DESC;
            """

            let statement = try prepareStatement(sql)
            defer { sqlite3_finalize(statement) }

            var logs: [DayLog] = []
            while sqlite3_step(statement) == SQLITE_ROW {
                logs.append(parseDayLogRow(from: statement))
            }
            return logs
        }
    }

    func upsertGoal(_ goal: Goal) throws {
        try queue.sync {
            let sql = """
            INSERT INTO goals (id, title, progress, deadline_ts, priority, created_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                progress = excluded.progress,
                deadline_ts = excluded.deadline_ts,
                priority = excluded.priority,
                created_ts = excluded.created_ts;
            """

            let statement = try prepareStatement(sql)
            defer { sqlite3_finalize(statement) }

            sqlite3_bind_text(statement, 1, (goal.id.uuidString as NSString).utf8String, -1, sqliteTransient)
            sqlite3_bind_text(statement, 2, (goal.title as NSString).utf8String, -1, sqliteTransient)
            sqlite3_bind_int(statement, 3, Int32(goal.progress))
            sqlite3_bind_double(statement, 4, goal.deadline.timeIntervalSince1970)
            sqlite3_bind_text(statement, 5, (goal.priority.rawValue as NSString).utf8String, -1, sqliteTransient)
            sqlite3_bind_double(statement, 6, goal.createdAt.timeIntervalSince1970)

            guard sqlite3_step(statement) == SQLITE_DONE else {
                throw DatabaseError.executionFailed(message: sqliteErrorMessage())
            }
        }
    }

    func fetchGoals() throws -> [Goal] {
        try queue.sync {
            let sql = """
            SELECT id, title, progress, deadline_ts, priority, created_ts
            FROM goals
            ORDER BY deadline_ts ASC;
            """

            let statement = try prepareStatement(sql)
            defer { sqlite3_finalize(statement) }

            var goals: [Goal] = []
            while sqlite3_step(statement) == SQLITE_ROW {
                let idText = textValue(statement, index: 0)
                let title = textValue(statement, index: 1)
                let progress = Int(sqlite3_column_int(statement, 2))
                let deadline = Date(timeIntervalSince1970: sqlite3_column_double(statement, 3))
                let priorityRaw = textValue(statement, index: 4)
                let createdAt = Date(timeIntervalSince1970: sqlite3_column_double(statement, 5))

                let goal = Goal(
                    id: UUID(uuidString: idText) ?? UUID(),
                    title: title,
                    progress: progress,
                    deadline: deadline,
                    priority: GoalPriority(rawValue: priorityRaw) ?? .medium,
                    createdAt: createdAt
                )

                goals.append(goal)
            }

            return goals
        }
    }

    func deleteGoal(id: UUID) throws {
        try queue.sync {
            let sql = "DELETE FROM goals WHERE id = ?;"
            let statement = try prepareStatement(sql)
            defer { sqlite3_finalize(statement) }

            sqlite3_bind_text(statement, 1, (id.uuidString as NSString).utf8String, -1, sqliteTransient)

            guard sqlite3_step(statement) == SQLITE_DONE else {
                throw DatabaseError.executionFailed(message: sqliteErrorMessage())
            }
        }
    }

    private static func openDatabase() throws -> OpaquePointer {
        let fileManager = FileManager.default
        let appSupportURL = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let folderURL = appSupportURL.appendingPathComponent("LifeOS", isDirectory: true)
        try fileManager.createDirectory(at: folderURL, withIntermediateDirectories: true)

        let dbURL = folderURL.appendingPathComponent("lifeos.sqlite")
        var dbPointer: OpaquePointer?

        if sqlite3_open(dbURL.path, &dbPointer) != SQLITE_OK {
            let message = dbPointer.map { String(cString: sqlite3_errmsg($0)) } ?? "Неизвестная ошибка"
            throw DatabaseError.openFailed(message: message)
        }

        guard let db = dbPointer else {
            throw DatabaseError.openFailed(message: "Пустой дескриптор базы данных")
        }

        return db
    }

    private func createTables() throws {
        let schema = """
        CREATE TABLE IF NOT EXISTS day_logs (
            date_key TEXT PRIMARY KEY,
            date_ts DOUBLE NOT NULL,
            reading_minutes INTEGER NOT NULL,
            deep_work_hours REAL NOT NULL,
            workout INTEGER NOT NULL,
            learning INTEGER NOT NULL,
            sleep_hours REAL NOT NULL,
            mood INTEGER NOT NULL,
            score INTEGER NOT NULL,
            analysis TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            progress INTEGER NOT NULL,
            deadline_ts DOUBLE NOT NULL,
            priority TEXT NOT NULL,
            created_ts DOUBLE NOT NULL
        );
        """

        try execute(schema)
    }

    private func execute(_ sql: String) throws {
        var errorMessage: UnsafeMutablePointer<Int8>?
        if sqlite3_exec(db, sql, nil, nil, &errorMessage) != SQLITE_OK {
            let message = errorMessage.map { String(cString: $0) } ?? sqliteErrorMessage()
            sqlite3_free(errorMessage)
            throw DatabaseError.executionFailed(message: message)
        }
    }

    private func prepareStatement(_ sql: String) throws -> OpaquePointer {
        var statement: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &statement, nil) != SQLITE_OK {
            throw DatabaseError.statementFailed(message: sqliteErrorMessage())
        }
        guard let statement else {
            throw DatabaseError.statementFailed(message: "Не удалось создать statement")
        }
        return statement
    }

    private func parseDayLogRow(from statement: OpaquePointer?) -> DayLog {
        let date = Date(timeIntervalSince1970: sqlite3_column_double(statement, 0))
        let readingMinutes = Int(sqlite3_column_int(statement, 1))
        let deepWorkHours = sqlite3_column_double(statement, 2)
        let workout = sqlite3_column_int(statement, 3) == 1
        let learning = sqlite3_column_int(statement, 4) == 1
        let sleepHours = sqlite3_column_double(statement, 5)
        let mood = Int(sqlite3_column_int(statement, 6))
        let score = Int(sqlite3_column_int(statement, 7))
        let analysis = textValue(statement, index: 8)

        return DayLog(
            date: date,
            readingMinutes: readingMinutes,
            deepWorkHours: deepWorkHours,
            workout: workout,
            learning: learning,
            sleepHours: sleepHours,
            mood: mood,
            score: score,
            analysis: analysis
        )
    }

    private func textValue(_ statement: OpaquePointer?, index: Int32) -> String {
        guard let cString = sqlite3_column_text(statement, index) else {
            return ""
        }
        return String(cString: cString)
    }

    private func sqliteErrorMessage() -> String {
        String(cString: sqlite3_errmsg(db))
    }
}
