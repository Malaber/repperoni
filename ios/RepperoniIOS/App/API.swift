import Foundation

enum RepperoniError: LocalizedError {
  case server(String)
  case unauthorized
  var errorDescription: String? {
    if case .server(let message) = self { return message }
    return "Session expired. Sign in again; your workout is saved."
  }
}

struct RepperoniAPI {
  let server: URL
  let token: String
  static var decoder: JSONDecoder {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return decoder
  }
  func data(_ path: String, method: String = "GET", body: Data? = nil) async throws -> Data {
    var request = URLRequest(
      url: URL(string: "api/v1/" + path, relativeTo: server.appending(path: "/"))!)
    request.httpMethod = method
    request.httpBody = body
    request.timeoutInterval = 20
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("1", forHTTPHeaderField: "X-Repperoni-CSRF")
    if !token.isEmpty { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
    let (data, response) = try await URLSession.shared.data(for: request)
    guard let response = response as? HTTPURLResponse else {
      throw RepperoniError.server("Server did not answer.")
    }
    if response.statusCode == 401 { throw RepperoniError.unauthorized }
    guard (200..<300).contains(response.statusCode) else {
      let detail =
        (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
      throw RepperoniError.server(detail ?? "Could not save. Check connection and retry.")
    }
    return data
  }
  func get<T: Decodable>(_ path: String) async throws -> T {
    try Self.decoder.decode(T.self, from: await data(path))
  }
  func send<T: Decodable>(_ path: String, body: [String: Any] = [:]) async throws -> T {
    try Self.decoder.decode(
      T.self,
      from: await data(path, method: "POST", body: JSONSerialization.data(withJSONObject: body)))
  }
}

struct Exercise: Decodable, Identifiable {
  let id: String
  let name: String
  let muscleGroup: String
  let equipment: String
}
struct LiftSet: Decodable, Identifiable {
  let id: String
  let setNumber: Int
  let weightKg: String
  let reps: Int
}
struct Performance: Decodable {
  let weightKg: String
  let reps: Int
}
struct Station: Decodable, Identifiable {
  let id: String
  let exercise: Exercise
  let sets: [LiftSet]
  let previousPerformance: Performance?
}
struct Workout: Decodable, Identifiable {
  let id: String
  let name: String
  let completedAt: String?
  let stations: [Station]
  let totalSets: Int
  let totalVolumeKg: String
}
struct WorkoutSummary: Decodable, Identifiable {
  let id: String
  let name: String
  let startedAt: String
  let totalSets: Int
  let totalVolumeKg: String
}
struct History: Decodable {
  let items: [WorkoutSummary]
  let nextCursor: String?
}
struct VolumePoint: Decodable, Identifiable {
  var id: String { date }
  let date: String
  let volumeKg: String
}
struct Record: Decodable, Identifiable {
  var id: String { exerciseId }
  let exerciseId: String
  let exerciseName: String
  let weightKg: String
  let reps: Int
}
struct Stats: Decodable {
  let workoutCount: Int
  let totalSets: Int
  let totalVolumeKg: String
  let currentStreak: Int
  let volumeByDay: [VolumePoint]
  let personalRecords: [Record]
}
