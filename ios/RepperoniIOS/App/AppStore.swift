import SwiftUI

@MainActor @Observable
final class AppStore {
  var credential: Credential?
  var workout: Workout?
  var exercises: [Exercise] = []
  var stats: Stats?
  var history: [WorkoutSummary] = []
  var error: String?
  var busy = false
  var message = "Every rep counts. Even the cheesy ones."
  private let signIn = BrowserSignIn()
  var api: RepperoniAPI? { credential.map { RepperoniAPI(server: $0.server, token: $0.token) } }

  init() {
    do { credential = try CredentialStore.read() } catch { self.error = error.localizedDescription }
    #if DEBUG
      if let token = ProcessInfo.processInfo.environment["REPPERONI_TEST_TOKEN"],
        let server = ProcessInfo.processInfo.environment["REPPERONI_TEST_SERVER"],
        let url = URL(string: server),
        url.host == "localhost" || url.host == "127.0.0.1"
      {
        credential = Credential(server: url, token: token, userID: "test")
      }
    #endif
  }
  func perform(_ action: () async throws -> Void) async {
    guard !busy else { return }
    busy = true
    error = nil
    defer { busy = false }
    do { try await action() } catch RepperoniError.unauthorized {
      do { try CredentialStore.remove() } catch {
        self.error = error.localizedDescription
        return
      }
      credential = nil
      workout = nil
      stats = nil
      history = []
      exercises = []
      error = RepperoniError.unauthorized.localizedDescription
    } catch { self.error = error.localizedDescription }
  }
  func login(_ address: String) async {
    await perform {
      guard let url = URL(string: address.trimmingCharacters(in: .whitespacesAndNewlines)),
        url.scheme == "https", url.host != nil, url.user == nil, url.password == nil,
        url.query == nil, url.fragment == nil, url.path.isEmpty || url.path == "/"
      else {
        throw RepperoniError.server("Enter your Repperoni HTTPS server address.")
      }
      let result = try await signIn.signIn(server: url)
      try CredentialStore.save(result)
      credential = result
      try await refresh()
    }
  }
  func refresh() async throws {
    guard let api else { return }
    workout = try await api.get("workouts/active")
    exercises = try await api.get("exercises")
    stats = try await api.get("stats/overview?days=30")
    let page: History = try await api.get("workouts")
    history = page.items
  }
  func start() async {
    await perform {
      guard let api else { return }
      workout = try await api.send("workouts", body: ["name": "Extra reps, extra cheese"])
    }
  }
  func add(_ exercise: Exercise) async {
    await perform {
      guard let api, let workout else { return }
      self.workout = try await api.send(
        "workouts/\(workout.id)/stations", body: ["exercise_id": exercise.id])
    }
  }
  func log(station: Station, weight: Double, reps: Int, mutation: String) async -> Bool {
    var saved = false
    await perform {
      guard let api, let workout else { return }
      let _: LiftSet = try await api.send(
        "workouts/\(workout.id)/stations/\(station.id)/sets",
        body: ["weight_kg": weight, "reps": reps, "client_mutation_id": mutation])
      saved = true
      message = "Set served. Chef's kiss."
      try await refresh()
    }
    return saved
  }
  func finish() async {
    await perform {
      guard let api, let workout else { return }
      let _: Workout = try await api.send("workouts/\(workout.id)/finish")
      message = "Workout baked to perfection."
      try await refresh()
    }
  }
  func logout() async {
    await perform {
      guard let api else { return }
      _ = try await api.data("auth/logout", method: "POST", body: Data("{}".utf8))
      try CredentialStore.remove()
      credential = nil
      workout = nil
      stats = nil
      history = []
      exercises = []
    }
  }
}
