import Charts
import SwiftUI

@main
struct RepperoniApp: App {
  @State private var store = AppStore()
  var body: some Scene { WindowGroup { RootView(store: store).tint(.orange) } }
}

struct RootView: View {
  @Bindable var store: AppStore
  @State private var server = "https://repperoni.malaber.de"
  var body: some View {
    Group {
      if store.credential == nil {
        NavigationStack {
          ScrollView {
            VStack(spacing: 24) {
              Image("Mascot").resizable().scaledToFit().frame(maxWidth: 240).accessibilityHidden(
                true)
              Text("Less tapping.\nMore topping.").font(.largeTitle.bold()).multilineTextAlignment(
                .center)
              Text("Log your reps. Chase your records. Become an absolute unit of pizza.")
                .multilineTextAlignment(.center)
              TextField("Server address", text: $server).textContentType(.URL).keyboardType(.URL)
                .textInputAutocapitalization(.never).autocorrectionDisabled().textFieldStyle(
                  .roundedBorder)
              Button("Sign in with passkey") { Task { await store.login(server) } }
                .buttonStyle(.borderedProminent).controlSize(.large).disabled(store.busy)
            }.padding(24).frame(maxWidth: 560).frame(maxWidth: .infinity)
          }.navigationTitle("Repperoni")
        }
      } else {
        TabView {
          TrainingView(store: store).tabItem { Label("Train", systemImage: "dumbbell.fill") }
          ProgressViewScreen(store: store).tabItem {
            Label("Progress", systemImage: "chart.bar.fill")
          }
          NavigationStack {
            List {
              Section("Your kitchen") { Text(store.credential?.server.absoluteString ?? "") }
              Section { Button("Sign out") { Task { await store.logout() } }.disabled(store.busy) }
            }.navigationTitle("Account")
          }.tabItem { Label("Account", systemImage: "person.crop.circle") }
        }
      }
    }
    .overlay(alignment: .top) {
      if store.busy { ProgressView().padding().background(.regularMaterial, in: Capsule()) }
    }
    .alert(
      "Hold the pepperoni",
      isPresented: Binding(get: { store.error != nil }, set: { if !$0 { store.error = nil } })
    ) {
      Button("OK") { store.error = nil }
    } message: {
      Text(store.error ?? "")
    }
    .task { await store.perform { try await store.refresh() } }
  }
}

struct TrainingView: View {
  @Bindable var store: AppStore
  @State private var choosing = false
  @State private var finishing = false
  @State private var search = ""
  var body: some View {
    NavigationStack {
      ScrollView {
        VStack(alignment: .leading, spacing: 20) {
          Text(store.message).font(.headline).foregroundStyle(.secondary).accessibilityIdentifier(
            "training-message")
          if let workout = store.workout {
            HStack {
              metric("SETS", "\(workout.totalSets)")
              Spacer()
              metric("VOLUME", "\(workout.totalVolumeKg) kg")
            }.padding().background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 20))
            if workout.stations.isEmpty {
              Text("Pick your first exercise. The dough won't lift itself.").font(.title2.bold())
            }
            ForEach(workout.stations) { station in
              StationCard(store: store, station: station)
            }
            Button {
              choosing = true
            } label: {
              Label("Add exercise", systemImage: "plus.circle.fill").frame(
                maxWidth: .infinity, minHeight: 44)
            }
            .buttonStyle(.borderedProminent).disabled(store.busy)
            Button {
              finishing = true
            } label: {
              Text("Finish workout").frame(maxWidth: .infinity, minHeight: 48)
            }.buttonStyle(.bordered).disabled(store.busy)
          } else {
            Image("Mascot").resizable().scaledToFit().frame(height: 210).frame(maxWidth: .infinity)
              .accessibilityHidden(true)
            Text("Ready to get shredded?").font(.largeTitle.bold())
            Text("Cheese optional. Showing up counts.").foregroundStyle(.secondary)
            Button("Start workout") { Task { await store.start() } }
              .buttonStyle(.borderedProminent).controlSize(.large).disabled(store.busy)
          }
        }.padding().frame(maxWidth: 680).frame(maxWidth: .infinity)
      }.navigationTitle("Fresh sets 🍕")
        .refreshable { await store.perform { try await store.refresh() } }
        .confirmationDialog(
          "Finish this workout?", isPresented: $finishing, titleVisibility: .visible
        ) {
          Button("Finish and save") { Task { await store.finish() } }
        } message: {
          Text("Your sets stay saved. Time to let the dough rest.")
        }
        .sheet(isPresented: $choosing) {
          NavigationStack {
            List(
              store.exercises.filter {
                search.isEmpty || $0.name.localizedCaseInsensitiveContains(search)
              }
            ) { exercise in
              Button {
                Task {
                  await store.add(exercise)
                  if store.error == nil { choosing = false }
                }
              } label: {
                VStack(alignment: .leading) {
                  Text(exercise.name).font(.headline)
                  Text("\(exercise.muscleGroup) · \(exercise.equipment)").font(.subheadline)
                    .foregroundStyle(.secondary)
                }.padding(.vertical, 8)
              }.disabled(store.busy)
            }.searchable(
              text: $search, placement: .navigationBarDrawer(displayMode: .always),
              prompt: "Find an exercise"
            ).navigationTitle(
              "Choose your topping"
            )
            .toolbar { Button("Done") { choosing = false } }
          }
        }
    }
  }
  private func metric(_ label: String, _ value: String) -> some View {
    VStack(alignment: .leading) {
      Text(label).font(.caption.bold())
      Text(value).font(.title2.bold()).monospacedDigit()
    }
  }
}

struct StationCard: View {
  @Bindable var store: AppStore
  let station: Station
  @State private var reps = 8
  @State private var weight = 20.0
  @State private var mutation = UUID().uuidString
  @State private var pending: (weight: Double, reps: Int)?
  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      Text(station.exercise.name).font(.title2.bold())
      if let last = station.previousPerformance {
        Text("Last time: \(last.weightKg) kg × \(last.reps)").font(.headline).foregroundStyle(
          .secondary)
      } else {
        Text("First serving. Make it a good one.").foregroundStyle(.secondary)
      }
      ForEach(station.sets) { set in
        Label(
          "Set \(set.setNumber) · \(set.weightKg) kg × \(set.reps)",
          systemImage: "checkmark.circle.fill"
        ).foregroundStyle(.green)
      }
      Stepper(value: $weight, in: 0...2000, step: 2.5) {
        Text("\(weight.formatted()) kg").font(.title.bold()).monospacedDigit()
      }.accessibilityLabel("Weight in kilograms").frame(minHeight: 48).disabled(pending != nil)
      Stepper(value: $reps, in: 1...1000) {
        Text("\(reps) reps").font(.largeTitle.bold()).monospacedDigit()
      }.accessibilityLabel("Repetitions").frame(minHeight: 48).disabled(pending != nil)
      Button(pending == nil ? "Log set" : "Retry saving set") {
        let payload = pending ?? (weight, reps)
        pending = payload
        Task {
          if await store.log(
            station: station, weight: payload.weight, reps: payload.reps, mutation: mutation)
          {
            pending = nil
            mutation = UUID().uuidString
            UINotificationFeedbackGenerator().notificationOccurred(.success)
          }
        }
      }.buttonStyle(.borderedProminent).controlSize(.large).disabled(store.busy)
    }.padding(20).background(
      Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 24)
    )
    .onAppear {
      if let last = station.sets.last {
        weight = Double(last.weightKg) ?? 20
        reps = last.reps
      } else if let last = station.previousPerformance {
        weight = Double(last.weightKg) ?? 20
        reps = last.reps
      }
    }
  }
}

struct ProgressViewScreen: View {
  @Bindable var store: AppStore
  var body: some View {
    NavigationStack {
      List {
        if let stats = store.stats {
          Section("Last 30 days · proof you showed up") {
            LabeledContent("Workouts", value: "\(stats.workoutCount)")
            LabeledContent("Sets served", value: "\(stats.totalSets)")
            LabeledContent("Volume", value: "\(stats.totalVolumeKg) kg")
            LabeledContent("Current streak", value: "\(stats.currentStreak)")
            Chart(stats.volumeByDay) { point in
              BarMark(
                x: .value("Day", String(point.date.suffix(5))),
                y: .value("Volume (kg)", Double(point.volumeKg) ?? 0)
              ).foregroundStyle(.orange)
            }.frame(height: 180).accessibilityLabel("Daily training volume")
          }
          Section("Personal bests. Extra crispy.") {
            if stats.personalRecords.isEmpty { Text("Your first set starts the story.") }
            ForEach(stats.personalRecords) { record in
              LabeledContent(record.exerciseName, value: "\(record.weightKg) kg × \(record.reps)")
            }
          }
        }
        Section("Recent workouts") {
          ForEach(store.history) { workout in
            VStack(alignment: .leading, spacing: 6) {
              Text(workout.name).font(.headline)
              Text(
                "\(workout.startedAt.prefix(10)) · \(workout.totalSets) sets · \(workout.totalVolumeKg) kg"
              ).foregroundStyle(.secondary)
            }.padding(.vertical, 6)
          }
        }
      }.navigationTitle("Dough you grow?")
        .refreshable { await store.perform { try await store.refresh() } }
    }
  }
}
